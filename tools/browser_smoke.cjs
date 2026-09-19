const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1280,height:720}});
 const errors=[];const logs=[];const checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{logs.push(m.type()+': '+m.text());if(m.text().includes('SCRIPT ERROR:')||m.text().includes('Parse Error:'))errors.push(m.text());});
 function check(ok,name){checks.push({name,pass:!!ok});if(!ok)throw Error(name);}
 try {
  await page.goto('http://127.0.0.1:8060',{waitUntil:'domcontentloaded',timeout:30000});
  await page.bringToFront();
  await page.waitForFunction(()=>window.__RIDGE?.floor===true,null,{timeout:90000});
  const initial=await page.evaluate(()=>window.__RIDGE);
  await page.waitForFunction(n=>window.__RIDGE.frames>n+20,initial.frames,{timeout:15000});
  check(true,'real exported Web game advances frames');
  await page.locator('canvas').click({position:{x:640,y:350}});
  await page.keyboard.down('Space');
  await page.waitForFunction(y=>window.__RIDGE.y>y+0.5,initial.y,{timeout:5000});
  await page.keyboard.up('Space');
  check(true,'keyboard jump changes real character elevation');
  await page.waitForFunction(()=>window.__RIDGE.floor,null,{timeout:10000});
  await page.keyboard.down('w');
  await page.waitForFunction(z=>window.__RIDGE.z<z-0.5,initial.z,{timeout:5000});
  await page.keyboard.up('w');
  check(true,'keyboard forward changes real character position');
  await page.keyboard.press('r');
  await page.waitForFunction(()=>Math.abs(window.__RIDGE.z)<0.1&&window.__RIDGE.falls===0,null,{timeout:5000});
  check(true,'restart resets gameplay position');
  await page.screenshot({path:'out/playtest.png'});
  check(errors.length===0,'no JavaScript or GDScript errors');
  fs.writeFileSync('out/browser.json',JSON.stringify({status:'PASS',checks,errors,renderer:'SwiftShader (not device FPS)',state:await page.evaluate(()=>window.__RIDGE)},null,2));
 }catch(e){
  fs.writeFileSync('out/browser.json',JSON.stringify({status:'FAIL',checks,errors,error:String(e)},null,2));
  await page.screenshot({path:'out/failed-browser.png'}).catch(()=>{});
  throw e;
 }finally{
  fs.writeFileSync('out/browser-console.log',logs.join('\n'));
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exit(1)});
