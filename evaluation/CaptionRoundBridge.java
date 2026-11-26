import java.io.*;
import java.util.Base64;
import dev.opencaption.opencaption.*;
public class CaptionRoundBridge {
  static String e(String s) { return Base64.getEncoder().encodeToString(s.getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
  static String d(String s) { return new String(Base64.getDecoder().decode(s), java.nio.charset.StandardCharsets.UTF_8); }
  public static void main(String[] args) throws Exception {
    var input = new BufferedReader(new InputStreamReader(System.in));
    for (String line; (line=input.readLine()) != null;) {
      String[] f=line.split("\t",-1);
      if (f[0].equals("prompt")) {
        System.out.println(e(CaptionStyle.INSTANCE.systemFor("bilingual", f[1]))+"\t"+e(E2eProtocol.INSTANCE.requestFor("bilingual","CS2 broadcast.")));
      } else if (f[0].equals("render")) {
        var r=CaptionStyle.INSTANCE.render(d(f[1]),d(f[2]),new CaptionStyle.Options(f[3],Boolean.parseBoolean(f[4])),true,true);
        System.out.println(e(r.getChinese())+"\t"+r.getNicknamesUsed()+"\t"+r.getPlayful());
      } else {
        var r=E2eProtocol.INSTANCE.parse(d(f[1]));
        if (r instanceof E2eProtocol.Result.Subtitle s) System.out.println("subtitle\t"+e(s.getEnglish())+"\t"+e(s.getChinese()));
        else if(r instanceof E2eProtocol.Result.Invalid i) System.out.println("invalid\t"+e(i.getReason()));
        else System.out.println("no_speech");
      }
      System.out.flush();
    }
  }
}
