import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import dev.opencaption.opencaption.*;
/** Thin calls into compiled production classes; no duplicated translation rules. */
public class CsDomainBridge {
 static String e(String s){return Base64.getEncoder().encodeToString(s.getBytes(StandardCharsets.UTF_8));}
 static String d(String s){return new String(Base64.getDecoder().decode(s),StandardCharsets.UTF_8);}
 public static void main(String[] args)throws Exception{
  Set<String> names=new HashSet<>(Files.readAllLines(Path.of(args[0])));
  var input=new BufferedReader(new InputStreamReader(System.in));
  for(String line;(line=input.readLine())!=null;){
   String[] f=line.split("\t",-1);
   switch(f[0]){
    case "choose"->{var r=E2eHintPolicy.INSTANCE.choose(Long.parseLong(f[1]),d(f[2]),Boolean.parseBoolean(f[3]));System.out.println(e(r.getHints())+"\t"+r.getVerification());}
    case "prompt"->System.out.println(e(CaptionStyle.INSTANCE.systemFor("bilingual","standard"))+"\t"+e(E2eProtocol.INSTANCE.requestFor("bilingual",d(f[1]))));
    case "parse"->{var r=E2eProtocol.INSTANCE.parseFor(d(f[2]),"bilingual",E2ePreservedNames.INSTANCE.forHints(d(f[1]),names));
     if(r instanceof E2eProtocol.Result.Subtitle s)System.out.println("subtitle\t"+e(s.getEnglish())+"\t"+e(s.getChinese()));
     else if(r instanceof E2eProtocol.Result.Invalid i)System.out.println("invalid\t"+e(i.getReason()));else System.out.println("no_speech");}
    case "render"->{var r=CaptionStyle.INSTANCE.render(d(f[1]),d(f[2]),new CaptionStyle.Options(f[3],Boolean.parseBoolean(f[4])),Boolean.parseBoolean(f[5]),Boolean.parseBoolean(f[6]));System.out.println(e(r.getChinese())+"\t"+r.getNicknamesUsed()+"\t"+r.getPlayful()+"\t"+r.getLocalizedPhrases());}
    default->throw new IllegalArgumentException("command");
   }System.out.flush();
  }
 }
}
