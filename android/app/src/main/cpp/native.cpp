#include <jni.h>
#include <android/log.h>
#include <atomic>
#include <cstring>
#include <string>
#include <vector>
#include <stdexcept>
#include <memory>
#include <unistd.h>
#include "whisper.h"
#include "llama.h"
#include "ggml-backend.h"
#ifdef OPENCAPTION_QWEN_E2E
#include "llm/llm.hpp"
#include <MNN/expr/ExprCreator.hpp>
#include <sstream>
#endif

namespace {
whisper_context *asr = nullptr;
whisper_vad_context *vad = nullptr;
llama_model *llm = nullptr;
llama_context *llm_ctx = nullptr;
std::atomic<bool> asr_cancelled{false};
std::atomic<bool> translation_cancelled{false};
std::atomic<bool> backend_initialized{false};
int threads = 4;
int diagnostic_fd = -1;
double last_no_speech_probability = 0;
double last_average_token_probability = 0;
#ifdef OPENCAPTION_QWEN_E2E
MNN::Transformer::Llm *omni = nullptr;
std::atomic<bool> omni_cancelled{false};
#endif
bool abort_asr(void *) { return asr_cancelled.load(); }
bool abort_translation(void *) { return translation_cancelled.load(); }
void stage(const std::string &message) {
    __android_log_print(ANDROID_LOG_INFO, "OpenCaptionNative", "%s", message.c_str());
    if (diagnostic_fd < 0) return;
    const std::string line = std::string("native ") + message + "\n";
    (void)::write(diagnostic_fd, line.data(), line.size());
    (void)::fsync(diagnostic_fd);
}
void native_log(enum ggml_log_level level, const char *text, void *) {
    if (!text) return;
    if (level == GGML_LOG_LEVEL_ERROR || level == GGML_LOG_LEVEL_WARN) {
        std::string msg(text);
        while (!msg.empty() && (msg.back() == '\n' || msg.back() == '\r')) msg.pop_back();
        if (!msg.empty()) {
            __android_log_print(
                level == GGML_LOG_LEVEL_ERROR ? ANDROID_LOG_ERROR : ANDROID_LOG_WARN,
                "OpenCaptionNative", "%s", msg.c_str());
            if (diagnostic_fd >= 0) {
                const std::string line = std::string("ggml[") +
                    (level == GGML_LOG_LEVEL_ERROR ? "E" : "W") + "] " + msg + "\n";
                (void)::write(diagnostic_fd, line.data(), line.size());
            }
        }
    }
}
llama_context *create_llm_context(llama_model *model, int n_threads) {
    auto cp = llama_context_default_params();
    cp.n_ctx = 1024;
    cp.n_batch = 512;
    cp.n_ubatch = 128;
    cp.n_threads = n_threads;
    cp.n_threads_batch = n_threads;
    cp.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_DISABLED;
    cp.offload_kqv = false;
    cp.op_offload = false;
    cp.abort_callback = abort_translation;
    cp.abort_callback_data = nullptr;
    return llama_init_from_model(model, cp);
}
bool trim_stop_marker(std::string &output, const char *marker) {
    const auto pos = output.find(marker);
    if (pos == std::string::npos) return false;
    output.resize(pos);
    return true;
}
std::string string_from_java(JNIEnv *env, jstring value) {
    auto cls = env->FindClass("java/lang/String");
    auto method = env->GetMethodID(cls, "getBytes", "(Ljava/lang/String;)[B");
    auto encoding = env->NewStringUTF("UTF-8");
    auto bytes = (jbyteArray) env->CallObjectMethod(value, method, encoding);
    const auto length = env->GetArrayLength(bytes);
    std::string result(length, '\0');
    env->GetByteArrayRegion(bytes, 0, length, reinterpret_cast<jbyte *>(result.data()));
    env->DeleteLocalRef(bytes); env->DeleteLocalRef(encoding); env->DeleteLocalRef(cls);
    return result;
}
jstring string_to_java(JNIEnv *env, const std::string &value) {
    auto bytes = env->NewByteArray(value.size());
    env->SetByteArrayRegion(bytes, 0, value.size(), reinterpret_cast<const jbyte *>(value.data()));
    auto cls = env->FindClass("java/lang/String");
    auto ctor = env->GetMethodID(cls, "<init>", "([BLjava/lang/String;)V");
    auto encoding = env->NewStringUTF("UTF-8");
    auto result = (jstring)env->NewObject(cls, ctor, bytes, encoding);
    env->DeleteLocalRef(bytes); env->DeleteLocalRef(encoding); env->DeleteLocalRef(cls);
    return result;
}
void fail(JNIEnv *env, const char *code) {
    env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), code);
}
std::vector<float> samples(JNIEnv *env, jfloatArray input) {
    std::vector<float> data(env->GetArrayLength(input));
    env->GetFloatArrayRegion(input, 0, data.size(), data.data());
    return data;
}
}

extern "C" JNIEXPORT void JNICALL
Java_dev_opencaption_opencaption_NativeEngine_load(JNIEnv *env, jobject,
    jstring asr_path, jstring vad_path, jstring llm_path, jint count, jint log_fd) {
    diagnostic_fd = log_fd;
    whisper_log_set(native_log, nullptr); llama_log_set(native_log, nullptr);
    if (!backend_initialized.exchange(true)) {
        llama_backend_init();
    }
    for (size_t i = 0; i < ggml_backend_dev_count(); ++i) {
        const auto device = ggml_backend_dev_get(i);
        stage(std::string("backend_device name=") + ggml_backend_dev_name(device) +
            " type=" + std::to_string(static_cast<int>(ggml_backend_dev_type(device))));
    }
    threads = count >= 2 && count <= 8 ? count : 4;
    asr_cancelled = false;
    translation_cancelled = false;
    const auto asr_model_path = string_from_java(env, asr_path);
    if (!asr_model_path.empty()) {
        // Run decoupled Whisper on ARMv8.2+fp16+dotprod CPU to avoid mobile
        // Vulkan Q5_1 driver crashes and SurfaceFlinger GPU UI freezes.
        auto cp = whisper_context_default_params();
        cp.use_gpu = false;
        cp.flash_attn = true;
        stage("asr_load_begin backend=cpu_armv82 flash_attn=1 threads=" + std::to_string(threads));
        asr = whisper_init_from_file_with_params(asr_model_path.c_str(), cp);
        if (!asr) { stage("asr_load_failed"); fail(env, "asr_model_load"); return; }
        stage("asr_load_ok");
    } else {
        stage("asr_load_skipped_external_onnx");
    }
    const auto vad_model_path = string_from_java(env, vad_path);
    if (!vad_model_path.empty()) {
        auto vp = whisper_vad_default_context_params(); vp.n_threads = 1; vp.use_gpu = false;
        stage("vad_load_begin");
        vad = whisper_vad_init_from_file_with_params(vad_model_path.c_str(), vp);
        if (!vad) { stage("vad_load_failed"); fail(env, "vad_model_load"); return; }
        stage("vad_load_ok");
    } else {
        stage("vad_load_skipped_energy_gate");
    }
    const auto path = string_from_java(env, llm_path);
    if (!path.empty()) {
        // Explicitly pass an empty GPU offload device list so llama_context
        // never initializes Vulkan0 or offloads n_tokens >= 32 ops onto mobile
        // Adreno GPU (which corrupted HY-MT1.5 Q4_K prefill when n >= 32).
        static ggml_backend_dev_t cpu_only_devices[1] = { nullptr };
        stage("translation_load_begin backend=cpu_only op_offload=0 threads=" + std::to_string(threads));
        auto mp = llama_model_default_params();
        mp.devices = cpu_only_devices;
        mp.n_gpu_layers = 0;
        mp.use_extra_bufts = false;
        llm = llama_model_load_from_file(path.c_str(), mp);
        if (llm) llm_ctx = create_llm_context(llm, threads);
        if (!llm || !llm_ctx) {
            if (llm_ctx) { llama_free(llm_ctx); llm_ctx = nullptr; }
            if (llm) { llama_model_free(llm); llm = nullptr; }
            stage("translation_load_failed");
            fail(env, "translation_model_load");
            return;
        }
        stage("translation_load_ok");
    }
    stage("native_load_complete");
}

extern "C" JNIEXPORT void JNICALL
Java_dev_opencaption_opencaption_NativeEngine_setCancelled(JNIEnv *, jobject, jboolean value) {
    asr_cancelled = value;
}

extern "C" JNIEXPORT void JNICALL
Java_dev_opencaption_opencaption_NativeEngine_setTranslationCancelled(JNIEnv *, jobject, jboolean value) {
    translation_cancelled = value;
}

extern "C" JNIEXPORT jdouble JNICALL
Java_dev_opencaption_opencaption_NativeEngine_voiceProbability(JNIEnv *env, jobject, jfloatArray input) {
    if (!vad) return 0;
    auto data = samples(env, input);
    if (!whisper_vad_detect_speech_no_reset(vad, data.data(), data.size())) {
        fail(env, "vad_inference"); return 0;
    }
    auto n = whisper_vad_n_probs(vad);
    return n ? whisper_vad_probs(vad)[n - 1] : 0;
}

extern "C" JNIEXPORT void JNICALL
Java_dev_opencaption_opencaption_NativeEngine_resetVad(JNIEnv *, jobject) {
    if (vad) whisper_vad_reset_state(vad);
}

extern "C" JNIEXPORT jstring JNICALL
Java_dev_opencaption_opencaption_NativeEngine_transcribe(JNIEnv *env, jobject,
    jfloatArray input, jstring hints, jstring language) {
    if (!asr) { fail(env, "asr_unavailable"); return nullptr; }
    auto data = samples(env, input);
    auto names = string_from_java(env, hints);
    auto lang = string_from_java(env, language);
    auto p = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    p.n_threads = threads;
    if (!whisper_is_multilingual(asr)) {
        p.language = "en";
    } else if (lang.empty() || lang == "auto") {
        p.language = "auto";
    } else {
        p.language = lang.c_str();
    }
    p.translate = false;
    p.no_context = true;
    p.single_segment = true;
    p.no_timestamps = true;
    p.max_tokens = 64;
    p.entropy_thold = 2.2f;
    p.no_speech_thold = 0.65f;
    p.print_progress = p.print_realtime = p.print_timestamps = p.print_special = false;
    p.initial_prompt = names.empty() ? nullptr : names.c_str();
    p.abort_callback = abort_asr; p.abort_callback_user_data = nullptr;
    p.suppress_nst = true; p.temperature_inc = 0;
    if (whisper_full(asr, p, data.data(), data.size()) != 0 || asr_cancelled) {
        fail(env, "asr_cancelled_or_failed"); return nullptr;
    }
    std::string text;
    double probability_sum = 0;
    int probability_count = 0;
    last_no_speech_probability = 0;
    for (int i = 0; i < whisper_full_n_segments(asr); i++) {
        text += whisper_full_get_segment_text(asr, i);
        last_no_speech_probability = std::max(
            last_no_speech_probability,
            static_cast<double>(whisper_full_get_segment_no_speech_prob(asr, i)));
        for (int j = 0; j < whisper_full_n_tokens(asr, i); j++) {
            const auto token = whisper_full_get_token_data(asr, i, j);
            if (token.p > 0) { probability_sum += token.p; probability_count++; }
        }
    }
    last_average_token_probability = probability_count ? probability_sum / probability_count : 0;
    return string_to_java(env, text);
}

extern "C" JNIEXPORT jdouble JNICALL
Java_dev_opencaption_opencaption_NativeEngine_lastNoSpeechProbability(JNIEnv *, jobject) {
    return last_no_speech_probability;
}

extern "C" JNIEXPORT jdouble JNICALL
Java_dev_opencaption_opencaption_NativeEngine_lastAverageTokenProbability(JNIEnv *, jobject) {
    return last_average_token_probability;
}

extern "C" JNIEXPORT jstring JNICALL
Java_dev_opencaption_opencaption_NativeEngine_translate(JNIEnv *env, jobject, jstring input) {
    if (!llm || !llm_ctx) { fail(env, "translation_unavailable"); return nullptr; }
    auto prompt = string_from_java(env, input);
    const auto *vocab = llama_model_get_vocab(llm);
    const int needed = -llama_tokenize(vocab, prompt.data(), prompt.size(), nullptr, 0, true, true);
    if (needed <= 0 || needed > 860) { fail(env, "context_too_long"); return nullptr; }
    std::vector<llama_token> tokens(needed);
    const auto n = llama_tokenize(vocab, prompt.data(), prompt.size(), tokens.data(), needed, true, true);
    if (n < 0) { fail(env, "tokenization_failed"); return nullptr; }
    stage("translation_tokens n=" + std::to_string(n) +
        " first=" + std::to_string(n > 0 ? tokens[0] : -1) +
        " last=" + std::to_string(n > 0 ? tokens[n - 1] : -1));
    llama_memory_clear(llama_get_memory(llm_ctx), true);
    for (int offset = 0; offset < n; offset += 512) {
        auto batch = llama_batch_get_one(tokens.data() + offset, std::min(512, n - offset));
        if (translation_cancelled || llama_decode(llm_ctx, batch) != 0) {
            fail(env, "translation_cancelled_or_failed"); return nullptr;
        }
    }
    auto sampler_params = llama_sampler_chain_default_params();
    auto sampler = std::unique_ptr<llama_sampler, decltype(&llama_sampler_free)>(
        llama_sampler_chain_init(sampler_params), llama_sampler_free);
    llama_sampler_chain_add(sampler.get(), llama_sampler_init_greedy());
    const auto eos_token = llama_vocab_eos(vocab);
    std::string output;
    llama_token prev_token = -1;
    int repeat_run = 0;
    for (int i = 0; i < 96; i++) {
        if (translation_cancelled) { fail(env, "translation_cancelled"); return nullptr; }
        auto token = llama_sampler_sample(sampler.get(), llm_ctx, -1);
        if (llama_vocab_is_eog(vocab, token) || (eos_token >= 0 && token == eos_token)) {
            return string_to_java(env, output);
        }
        if (token == prev_token) {
            if (++repeat_run >= 6) {
                stage("translation_repeat_abort");
                break;
            }
        } else {
            prev_token = token;
            repeat_run = 1;
        }
        std::vector<char> piece(256);
        int size = llama_token_to_piece(vocab, token, piece.data(), piece.size(), 0, false);
        if (size < 0) {
            piece.resize(-size);
            size = llama_token_to_piece(vocab, token, piece.data(), piece.size(), 0, false);
        }
        if (size > 0) output.append(piece.data(), size);
        if (trim_stop_marker(output, "<｜hy_place▁holder▁no▁2｜>") ||
            trim_stop_marker(output, "<|im_end|>")) {
            return string_to_java(env, output);
        }
        if (output.find('\n') != std::string::npos && output.size() > 4) {
            output.resize(output.find('\n'));
            return string_to_java(env, output);
        }
        auto batch = llama_batch_get_one(&token, 1);
        if (llama_decode(llm_ctx, batch) != 0) {
            fail(env, "translation_cancelled_or_failed"); return nullptr;
        }
    }
    // A small model can omit EOS even after producing a usable answer. Return
    // the bounded text and let the strict Dart parser accept only real Chinese.
    stage(std::string("translation_token_limit preview=") + output.substr(0, 320));
    return string_to_java(env, output);
}

extern "C" JNIEXPORT void JNICALL
Java_dev_opencaption_opencaption_NativeEngine_release(JNIEnv *, jobject) {
    stage("release_begin");
    // Called only after capture/VAD and the heavy worker have stopped.
    if (asr) { whisper_free(asr); asr = nullptr; }
    if (vad) { whisper_vad_free(vad); vad = nullptr; }
    if (llm_ctx) { llama_free(llm_ctx); llm_ctx = nullptr; }
    if (llm) { llama_model_free(llm); llm = nullptr; }
    stage("release_complete");
}

#ifdef OPENCAPTION_QWEN_E2E
extern "C" JNIEXPORT void JNICALL
Java_dev_opencaption_opencaption_NativeEngine_loadOmni(JNIEnv *env, jobject, jstring model_path) {
    if (omni) { MNN::Transformer::Llm::destroy(omni); omni = nullptr; }
    const auto root = string_from_java(env, model_path);
    const auto config = root + (root.back() == '/' ? "opencaption_config.json" : "/opencaption_config.json");
    omni = MNN::Transformer::Llm::createLLM(config);
    if (!omni || !omni->load()) {
        if (omni) { MNN::Transformer::Llm::destroy(omni); omni = nullptr; }
        fail(env, "omni_model_load");
    }
    omni->set_config("{\"max_new_tokens\":96,\"sampler_type\":\"greedy\"}");
    omni_cancelled = false;
}

extern "C" JNIEXPORT jstring JNICALL
Java_dev_opencaption_opencaption_NativeEngine_transcribeTranslateOmni(
    JNIEnv *env, jobject, jfloatArray input) {
    if (!omni) { fail(env, "omni_unavailable"); return nullptr; }
    auto data = samples(env, input);
    auto waveform = MNN::Express::_Const(
        data.data(), {static_cast<int>(data.size())}, MNN::Express::NCHW,
        halide_type_of<float>());
    MNN::Transformer::MultimodalPrompt prompt;
    prompt.prompt_template =
        "<audio>speech</audio>\nIf there is no intelligible English speech, output exactly NO_SPEECH. "
        "Otherwise transcribe the speech in English, then translate it into Mainland China Simplified Chinese (简体中文, zh-CN). "
        "Do NOT output Traditional Chinese (繁體中文). "
        "Output exactly two lines: English: ... and Chinese: ... Do not think aloud.";
    prompt.audios["speech"] = {"", waveform};
    std::ostringstream output;
    omni->reset();
    omni->response(prompt, &output, nullptr, 96);
    if (omni_cancelled) { fail(env, "omni_cancelled"); return nullptr; }
    return string_to_java(env, output.str());
}

extern "C" JNIEXPORT void JNICALL
Java_dev_opencaption_opencaption_NativeEngine_setOmniCancelled(JNIEnv *, jobject, jboolean value) {
    omni_cancelled = value;
}

extern "C" JNIEXPORT void JNICALL
Java_dev_opencaption_opencaption_NativeEngine_releaseOmni(JNIEnv *, jobject) {
    if (omni) { MNN::Transformer::Llm::destroy(omni); omni = nullptr; }
}
#else
extern "C" JNIEXPORT void JNICALL Java_dev_opencaption_opencaption_NativeEngine_loadOmni(JNIEnv *env, jobject, jstring) { fail(env, "omni_not_built"); }
extern "C" JNIEXPORT jstring JNICALL Java_dev_opencaption_opencaption_NativeEngine_transcribeTranslateOmni(JNIEnv *env, jobject, jfloatArray) { fail(env, "omni_not_built"); return nullptr; }
extern "C" JNIEXPORT void JNICALL Java_dev_opencaption_opencaption_NativeEngine_setOmniCancelled(JNIEnv *, jobject, jboolean) {}
extern "C" JNIEXPORT void JNICALL Java_dev_opencaption_opencaption_NativeEngine_releaseOmni(JNIEnv *, jobject) {}
#endif
