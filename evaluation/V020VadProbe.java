import dev.opencaption.opencaption.SileroBoundaryVad;
import dev.opencaption.opencaption.E2eSegmenter;
import java.nio.file.*;
import java.util.*;
import javax.sound.sampled.*;

/** Actual product Kotlin adapter, Linux ORT. Never substitutes Android timing. */
public class V020VadProbe {
  static void require(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }
  public static void main(String[] args) throws Exception {
    Path root = Path.of(args[0]);
    byte[] model = Files.readAllBytes(root.resolve("android/app/src/main/assets/vad/silero_v6_2_1.onnx"));
    float[] audio;
    try (AudioInputStream stream = AudioSystem.getAudioInputStream(root.resolve("evaluation/results/s0-20261013/clip.wav").toFile())) {
      AudioFormat f = stream.getFormat();
      require(f.getSampleRate()==16000 && f.getChannels()==1 && f.getSampleSizeInBits()==16 && !f.isBigEndian(), "PCM format");
      byte[] bytes=stream.readAllBytes(); audio=new float[bytes.length/2];
      for (int i=0;i<audio.length;i++) audio[i]=(short)((bytes[i*2]&255)|(bytes[i*2+1]<<8))/32768f;
    }
    String[] numbers = Files.readString(root.resolve("evaluation/results/s0-20261013/clip_vad.json")).replace("[", "").replace("]", "").trim().split(",");
    double[] expected=Arrays.stream(numbers).mapToDouble(Double::parseDouble).toArray();
    long init=System.nanoTime();
    try (SileroBoundaryVad vad=new SileroBoundaryVad(model)) {
      double initMs=(System.nanoTime()-init)/1e6;
      double delta=0;
      for (int off=0, index=0;off<audio.length;off+=512,index++) {
        float[] frame=Arrays.copyOfRange(audio,off,off+512);
        delta=Math.max(delta, Math.abs(vad.observe(frame)-expected[index]));
      }
      require(delta<1e-6,"JVM probability vs cached Python: "+delta);
      vad.reset();
      E2eSegmenter segmenter=new E2eSegmenter();
      List<E2eSegmenter.Boundary> boundaries=new ArrayList<>();
      long began=System.nanoTime(); double frameDelta=0; int calls=0;
      for (int off=0;off<audio.length;off+=320) {
        int end=Math.min(off+320,audio.length);
        double p=vad.observe(Arrays.copyOfRange(audio,off,end)); calls++;
        int index=end/512-1;
        frameDelta=Math.max(frameDelta,Math.abs(p-(index<0?0:expected[index])));
        var boundary=segmenter.update(end,p);
        if (boundary!=null) boundaries.add(boundary);
      }
      var tail=segmenter.flush(audio.length); if(tail!=null) boundaries.add(tail);
      double elapsedMs=(System.nanoTime()-began)/1e6;
      require(frameDelta<1e-6,"320-sample streaming parity: "+frameDelta);
      long last=0; int pauses=0;
      for (var b:boundaries) {
        require(b.getStart()==last && b.getEnd()>last && b.getEnd()-last<=80000,"sample ownership");
        last=b.getEnd(); if(b.getReason().equals("pause")) pauses++;
        System.out.printf(Locale.ROOT,"boundary start=%d end=%d reason=%s%n",b.getStart(),b.getEnd(),b.getReason());
      }
      require(last==audio.length,"tail retained");
      // Exact-zero and nonzero weak inputs exercise the adapter rather than a gate.
      vad.reset(); double zero=vad.observe(new float[512]);
      require(Double.isFinite(zero) && zero>=0 && zero<=1,"zero probability");
      float[] weak=new float[320]; Arrays.fill(weak,1f/32768f);
      require(Double.isFinite(vad.observe(weak)),"nonzero weak probability");
      System.out.printf(Locale.ROOT,"{\"scope\":\"Linux JVM actual Kotlin adapter; no Android timing\",\"samples\":%d,\"calls_20ms\":%d,\"windows\":%d,\"pauses\":%d,\"init_ms\":%.3f,\"elapsed_ms\":%.3f,\"rtf\":%.6f,\"max_delta\":%.9f,\"frame_delta\":%.9f}%n",audio.length,calls,boundaries.size(),pauses,initMs,elapsedMs,elapsedMs/(audio.length/16.0),delta,frameDelta);
    }
  }
}
