import dev.opencaption.opencaption.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Product parser including packaged-name allowlist, unlike the older bridge. */
public class V020JointProtocolBridge {
  public static void main(String[] args) throws Exception {
    var names=E2ePreservedNames.INSTANCE.bounded(Files.readAllLines(Path.of(args[0])));
    var reader=new BufferedReader(new InputStreamReader(System.in));
    for(String line;(line=reader.readLine())!=null;) {
      String[] f=line.split("\t",-1);
      String hints=V020ProtocolBridge.decode(f[2]);
      if(f[0].equals("prompt")) System.out.println(V020ProtocolBridge.encode(E2eProtocol.INSTANCE.systemFor(f[1]))+"\t"+V020ProtocolBridge.encode(E2eProtocol.INSTANCE.requestFor(f[1],hints)));
      else {
        var result=E2eProtocol.INSTANCE.parseFor(V020ProtocolBridge.decode(f[3]),f[1],E2ePreservedNames.INSTANCE.forHints(hints,names));
        if(result instanceof E2eProtocol.Result.Subtitle s) System.out.println("subtitle\t"+V020ProtocolBridge.encode(s.getEnglish())+"\t"+V020ProtocolBridge.encode(s.getChinese()));
        else if(result instanceof E2eProtocol.Result.Invalid bad) System.out.println("invalid\t"+V020ProtocolBridge.encode(bad.getReason()));
        else System.out.println("no_speech");
      }
      System.out.flush();
    }
  }
}
