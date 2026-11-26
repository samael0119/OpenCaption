import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import dev.opencaption.opencaption.CsPromptFinal;
public class CsPromptFinalBridge {
 public static void main(String[] args)throws Exception{
  var in=new BufferedReader(new InputStreamReader(System.in));
  for(String line;(line=in.readLine())!=null;){
   String hints=new String(Base64.getDecoder().decode(line),StandardCharsets.UTF_8);
   System.out.println(Base64.getEncoder().encodeToString(CsPromptFinal.SYSTEM.getBytes(StandardCharsets.UTF_8))+"\t"+Base64.getEncoder().encodeToString(CsPromptFinal.INSTANCE.request(hints).getBytes(StandardCharsets.UTF_8)));System.out.flush();
  }
 }
}
