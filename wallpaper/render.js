const {chromium}=require('playwright');const path=require('path');
(async()=>{const b=await chromium.launch();const pg=await b.newPage({viewport:{width:1320,height:2868},deviceScaleFactor:1});
const f='file://'+path.resolve('wallpaper.html');
for(const m of ['lock','home']){await pg.goto(f+'?mode='+m);await pg.locator('canvas').screenshot({path:`burgundy-${m}.png`});}
await pg.goto(f+'?mode=lock&t=0');require('fs').mkdirSync('frames',{recursive:true});
const F=90;for(let i=0;i<F;i++){const t=Math.min(1,0.55+0.45*(i/(F-15)));await pg.evaluate(t=>draw(t),t);await pg.locator('canvas').screenshot({path:`frames/f${String(i).padStart(3,'0')}.png`,type:'png'});}
await b.close()})();
