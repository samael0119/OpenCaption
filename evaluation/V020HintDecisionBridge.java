import dev.opencaption.opencaption.E2eHintPolicy;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/** Calls the compiled product hint cadence; no duplicate policy in Python. */
public class V020HintDecisionBridge {
  public static void main(String[] args) throws Exception {
    var input = new BufferedReader(new InputStreamReader(System.in));
    for (String line; (line = input.readLine()) != null;) {
      String[] fields = line.split("\t", -1);
      String hints = new String(Base64.getDecoder().decode(fields[2]), StandardCharsets.UTF_8);
      var decision = E2eHintPolicy.INSTANCE.choose(Long.parseLong(fields[0]), hints, Boolean.parseBoolean(fields[1]));
      System.out.println(Base64.getEncoder().encodeToString(decision.getHints().getBytes(StandardCharsets.UTF_8)) + "\t" + decision.getVerification());
      System.out.flush();
    }
  }
}
