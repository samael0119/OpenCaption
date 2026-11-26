import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import dev.opencaption.opencaption.*;
public class CsPromptProbeBridge {
 static String e(String s){return Base64.getEncoder().encodeToString(s.getBytes(StandardCharsets.UTF_8));}
 static String d(String s){return new String(Base64.getDecoder().decode(s),StandardCharsets.UTF_8);}
 public static void main(String[] args)throws Exception {
  var in=new BufferedReader(new InputStreamReader(System.in));
  for(String line;(line=in.readLine())!=null;){
   var f=line.split("\t",-1);
   if(f[0].equals("prompt"))System.out.println(e(CsPromptCandidates.INSTANCE.system(f[1]))+"\t"+e(CsPromptCandidates.INSTANCE.request(f[1],d(f[2]))));
   else throw new IllegalArgumentException("command");
   System.out.flush();
  }
 }
}
