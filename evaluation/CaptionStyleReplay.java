import java.io.*;
import java.util.Base64;
import dev.opencaption.opencaption.CaptionStyle;
public class CaptionStyleReplay {
  static String e(String s) { return Base64.getEncoder().encodeToString(s.getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
  static String d(String s) { return new String(Base64.getDecoder().decode(s), java.nio.charset.StandardCharsets.UTF_8); }
  public static void main(String[] args) throws Exception {
    var input=new BufferedReader(new InputStreamReader(System.in));
    for(String line; (line=input.readLine())!=null;) {
      var f=line.split("\t",-1);
      var r=CaptionStyle.INSTANCE.render(d(f[0]),d(f[1]),new CaptionStyle.Options(f[2],Boolean.parseBoolean(f[3])),Boolean.parseBoolean(f[4]),Boolean.parseBoolean(f[5]));
      System.out.println(e(r.getChinese())+"\t"+r.getNicknamesUsed()+"\t"+r.getPlayful()+"\t"+r.getLocalizedPhrases());
      System.out.flush();
    }
  }
}
