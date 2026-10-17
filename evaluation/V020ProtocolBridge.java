import dev.opencaption.opencaption.E2eProtocol;
import java.io.*;
import java.util.Base64;

/** Actual product prompt/parser without Android services or a second model. */
public class V020ProtocolBridge {
  static String encode(String s) { return Base64.getEncoder().encodeToString(s.getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
  static String decode(String s) { return new String(Base64.getDecoder().decode(s), java.nio.charset.StandardCharsets.UTF_8); }
  public static void main(String[] args) throws Exception {
    var input=new BufferedReader(new InputStreamReader(System.in));
    for(String line;(line=input.readLine())!=null;) {
      String[] fields=line.split("\t",-1);
      if(fields[0].equals("prompt")) {
        System.out.println(encode(E2eProtocol.INSTANCE.systemFor(fields[1]))+"\t"+encode(E2eProtocol.INSTANCE.requestFor(fields[1],decode(fields[2]))));
      } else {
        var result=E2eProtocol.INSTANCE.parseFor(decode(fields[2]),fields[1]);
        if(result instanceof E2eProtocol.Result.Subtitle s) System.out.println("subtitle\t"+encode(s.getEnglish())+"\t"+encode(s.getChinese()));
        else if(result instanceof E2eProtocol.Result.Invalid bad) System.out.println("invalid\t"+encode(bad.getReason()));
        else System.out.println("no_speech");
      }
      System.out.flush();
    }
  }
}
