import dev.opencaption.opencaption.SileroBoundaryVad;
import java.nio.file.*;
import java.util.*;
import javax.sound.sampled.*;

/** Frozen public cases, reset and continuous VAD; no caption filtering. */
public class V020SpeechEvidenceProbe {
  public static void main(String[] args) throws Exception {
    Path root = Path.of(args[0]);
    List<String> cases = Files.readAllLines(Path.of(args[1]));
    byte[] model = Files.readAllBytes(root.resolve("android/app/src/main/assets/vad/silero_v6_2_1.onnx"));
    System.out.println("#scope\tLinux Kotlin VAD diagnostic; no product filter or Android timing claim");
    try (SileroBoundaryVad vad = new SileroBoundaryVad(model)) {
      for (String mode : List.of("reset", "continuous")) {
        vad.reset();
        for (String line : cases) {
          String[] fields = line.split("\t");
          if (fields.length != 3) throw new IllegalArgumentException("case columns");
          if (mode.equals("reset")) vad.reset();
          float[] audio;
          try (AudioInputStream stream = AudioSystem.getAudioInputStream(root.resolve(fields[2]).toFile())) {
            AudioFormat f = stream.getFormat();
            if (f.getSampleRate()!=16000 || f.getChannels()!=1 || f.getSampleSizeInBits()!=16 || f.isBigEndian())
              throw new IllegalArgumentException("PCM format");
            byte[] bytes = stream.readAllBytes();
            if (bytes.length == 0 || bytes.length > 160000) throw new IllegalArgumentException("case duration");
            audio = new float[bytes.length/2];
            for (int i=0; i<audio.length; i++) audio[i]=(short)((bytes[i*2]&255)|(bytes[i*2+1]<<8))/32768f;
          }
          double peak=0, sum=0, energy=0; int calls=0, aboveHalf=0;
          long began=System.nanoTime();
          for (float sample : audio) energy += sample*sample;
          for (int off=0; off<audio.length; off+=320) {
            double probability=vad.observe(Arrays.copyOfRange(audio,off,Math.min(off+320,audio.length)));
            if (!Double.isFinite(probability) || probability<0 || probability>1) throw new IllegalStateException("invalid VAD");
            peak=Math.max(peak,probability); sum+=probability; calls++;
            if (probability>=.5) aboveHalf++;
          }
          System.out.printf(Locale.ROOT,"%s\t%s\t%s\t%d\t%.9f\t%.9f\t%.9f\t%d\t%.3f%n",
            mode,fields[0],fields[1],audio.length,Math.sqrt(energy/audio.length),peak,sum/calls,aboveHalf,(System.nanoTime()-began)/1e6);
        }
      }
    }
    System.out.println("#complete\t"+(cases.size()*2));
  }
}
