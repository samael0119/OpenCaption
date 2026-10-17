const fs=require('fs'),path=require('path');
const {chromium}=require('/home/hyh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const dir=path.resolve(process.argv[2]),url='http://127.0.0.1:8767';
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage','--disable-background-timer-throttling']});
 const context=await browser.newContext({viewport:{width:390,height:780}});let page=null,last=-1;
 async function post(endpoint,row){const r=await fetch(url+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(row)});if(!r.ok)throw Error(endpoint+' '+r.status);}
 try {
  while(true){
   const s=await fetch(url+'/status').then(r=>r.json());
   if(s.phase==='stop')break;
   if(s.phase==='prepare'&&s.batch!==last){
    if(page)await page.close();page=await context.newPage();last=s.batch;
    page.on('pageerror',e=>fs.appendFileSync(path.join(dir,'browser_errors.jsonl'),JSON.stringify({batch:last,error:String(e)})+'\n'));
    await page.goto(url+'/?theme=dark&run=batch-'+last);
    await page.waitForFunction(()=>window.deliveryBridge?.rows.some(r=>r.type==='installed'),null,{timeout:30000});
    const clock=await page.evaluate(()=>window.deliveryBridge.sync());
    if(clock.rtt>=50)throw Error('clock interval too wide before replay');
    await post('/ui_ready',{batch:last,clock,display:'headful Chromium/Xvfb virtual raster, not physical scanout'});
   }
   if(s.phase==='drain'&&page&&s.batch===last){
    await page.evaluate(async()=>{await new Promise(r=>setTimeout(r,1700));await window.deliveryBridge.sync();});
    await page.screenshot({path:path.join(dir,'batch-'+last+'.png')});
    const rows=await page.evaluate(()=>{const rows=window.deliveryBridge.rows.slice();window.deliveryBridge.stop();return rows;});
    fs.writeFileSync(path.join(dir,'batch-'+last+'-browser.json'),JSON.stringify(rows,null,2));
    await page.close();page=null;await post('/ui_done',{batch:last,rows:rows.length});
   }
   await new Promise(r=>setTimeout(r,100));
  }
 }finally {if(page)await page.close();await context.close();await browser.close();}
})().catch(e=>{fs.appendFileSync(path.join(dir,'browser_errors.jsonl'),JSON.stringify({fatal:String(e)})+'\n');console.error(e);process.exitCode=1;});
