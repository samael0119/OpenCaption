cmake_minimum_required(VERSION 3.22)
project(opencaption LANGUAGES C CXX)
# Keep the first build safe on the 12 GB development host. Ninja otherwise
# launches one memory-heavy compiler per core, in addition to the Gradle JVM.
set_property(GLOBAL PROPERTY JOB_POOLS caption_compile=8 caption_link=1)
set(CMAKE_JOB_POOL_COMPILE caption_compile)
set(CMAKE_JOB_POOL_LINK caption_link)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
# Flutter's debug variant otherwise builds GGML/Whisper/llama with -O0,
# making a short Whisper window take tens of seconds on the target phone.
# Keep Dart/JNI diagnostics while compiling all native inference code at a
# representative optimization level and without bulky native debug symbols.
if(ANDROID)
  add_compile_options(
    "$<$<CONFIG:Debug>:-O2>"
    "$<$<CONFIG:Debug>:-g0>"
  )
endif()
set(CMAKE_C_VISIBILITY_PRESET hidden)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
set(GGML_CPU_ALL_VARIANTS OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN ON CACHE BOOL "" FORCE)
if(ANDROID)
  set(Vulkan_GLSLC_EXECUTABLE
    "${CMAKE_ANDROID_NDK}/shader-tools/linux-x86_64/glslc"
    CACHE FILEPATH "Android NDK glslc" FORCE)
endif()
set(GGML_BACKEND_DL OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_COMMON OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
get_filename_component(REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../../.." ABSOLUTE)
if(NOT EXISTS "${REPO_ROOT}/third_party/llama.cpp/CMakeLists.txt")
  message(FATAL_ERROR "Run python3 scripts/fetch_native.py before building")
endif()
if(NOT EXISTS "${REPO_ROOT}/third_party/Vulkan-Headers/include/vulkan/vulkan.hpp")
  message(FATAL_ERROR "Run python3 scripts/fetch_native.py to install Vulkan-Headers")
endif()
# The Android NDK ships the C Vulkan headers but not Vulkan-Hpp, which the
# ggml Vulkan backend uses. Keep the headers pinned with the other native deps.
include_directories(SYSTEM "${REPO_ROOT}/third_party/Vulkan-Headers/include")
include_directories(SYSTEM "${REPO_ROOT}/third_party/SPIRV-Headers/include")
set(SPIRV_HEADERS_ENABLE_TESTS OFF CACHE BOOL "" FORCE)
set(SPIRV_HEADERS_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory("${REPO_ROOT}/third_party/SPIRV-Headers" "spirv-headers" EXCLUDE_FROM_ALL)
# A single pinned GGML implementation avoids duplicate backend registries.
# whisper.cpp reuses the existing ggml target. Both engines are built together.
add_subdirectory("${REPO_ROOT}/third_party/llama.cpp" "llama" EXCLUDE_FROM_ALL)
add_subdirectory("${REPO_ROOT}/third_party/whisper.cpp" "whisper" EXCLUDE_FROM_ALL)
add_library(opencaption SHARED native.cpp)
target_link_libraries(opencaption PRIVATE whisper llama android log)
if(OPENCAPTION_QWEN_E2E)
  # MNN's Android post-build rules require real library targets (not OBJECT
  # targets), and its Snapdragon path is OpenCL. Shared component libraries are
  # packaged transitively by AGP together with libopencaption.so.
  set(MNN_BUILD_SHARED_LIBS ON CACHE BOOL "" FORCE)
  set(MNN_SEP_BUILD ON CACHE BOOL "" FORCE)
  set(MNN_OPENCL ON CACHE BOOL "" FORCE)
  set(MNN_KLEIDIAI_DEFAULT_ON ON CACHE BOOL "" FORCE)
  set(MNN_BUILD_LLM ON CACHE BOOL "" FORCE)
  set(MNN_BUILD_LLM_OMNI ON CACHE BOOL "" FORCE)
  set(MNN_BUILD_AUDIO ON CACHE BOOL "" FORCE)
  set(MNN_BUILD_OPENCV OFF CACHE BOOL "" FORCE)
  set(MNN_LLM_BUILD_DEMO OFF CACHE BOOL "" FORCE)
  set(LLM_SUPPORT_HTTP_RESOURCE OFF CACHE BOOL "" FORCE)
  set(MNN_BUILD_TEST OFF CACHE BOOL "" FORCE)
  set(MNN_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
  add_subdirectory("${REPO_ROOT}/third_party/MNN" "mnn" EXCLUDE_FROM_ALL)
  target_compile_definitions(opencaption PRIVATE OPENCAPTION_QWEN_E2E)
  target_include_directories(opencaption PRIVATE
    "${REPO_ROOT}/third_party/MNN/include"
    "${REPO_ROOT}/third_party/MNN/express"
    "${REPO_ROOT}/third_party/MNN/transformers/llm/engine/include"
  )
  target_link_libraries(opencaption PRIVATE llm MNN MNNAudio)
endif()
target_link_options(opencaption PRIVATE "-Wl,--exclude-libs,ALL" "-Wl,-z,max-page-size=16384")
