import dev.opencaption.opencaption.CaptionStyle;
import dev.opencaption.opencaption.E2eProtocol;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/** Runs the Android default prompt and parser in the offline P0 probe. */
public class E2bP0Bridge {
  private static String encode(String text) {
    return Base64.getEncoder().encodeToString(text.getBytes(StandardCharsets.UTF_8));
  }

  public static void main(String[] args) throws Exception {
    var input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
    for (String line; (line = input.readLine()) != null;) {
      String[] fields = line.split("\t", -1);
      String text = new String(Base64.getDecoder().decode(fields[1]), StandardCharsets.UTF_8);
      switch (fields[0]) {
        case "prompt" -> System.out.println("prompt\t" +
            encode(CaptionStyle.INSTANCE.systemFor("bilingual", "standard")) + "\t" +
            encode(E2eProtocol.INSTANCE.requestFor("bilingual", text)));
        case "parse" -> {
          var result = E2eProtocol.INSTANCE.parse(text);
          if (result instanceof E2eProtocol.Result.Subtitle subtitle) {
            System.out.println("subtitle\t" + encode(subtitle.getEnglish()) + "\t" + encode(subtitle.getChinese()));
          } else if (result instanceof E2eProtocol.Result.Invalid invalid) {
            System.out.println("invalid\t" + encode(invalid.getReason()));
          } else {
            System.out.println("no_speech");
          }
        }
        default -> throw new IllegalArgumentException("Unknown probe command");
      }
      System.out.flush();
    }
  }
}
