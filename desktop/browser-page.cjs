"use strict";
// These scripts operate only on the rendered official post, never hidden API data.
const helpers = `
 const main=document.querySelector('main');
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>=24&&r.height>=20&&r.top<innerHeight&&r.bottom>0&&r.left<innerWidth&&r.right>0&&s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0'};
 const area=e=>{const r=e.getBoundingClientRect();return Math.max(0,Math.min(r.right,innerWidth)-Math.max(r.left,0))*Math.max(0,Math.min(r.bottom,innerHeight)-Math.max(r.top,0))};
 const candidates=main?Array.from(main.querySelectorAll('video,img')).filter(e=>visible(e)&&!e.closest('a[href*="/reel/"],a[href*="/p/"],[role=dialog]')&&e.getBoundingClientRect().width>=250&&e.getBoundingClientRect().height>=200):[];
 candidates.sort((a,b)=>area(b)-area(a));
 const primary=candidates[0];
 const next=main&&primary?Array.from(main.querySelectorAll('button,[role=button]')).find(e=>{const label=e.getAttribute('aria-label')||e.querySelector('svg')?.getAttribute('aria-label')||e.textContent;const r=e.getBoundingClientRect(),p=primary.getBoundingClientRect();return /^(Next|다음)$/.test(label?.trim()||'')&&visible(e)&&r.left>=p.left&&r.right<=p.right+50&&r.top>=p.top&&r.bottom<=p.bottom}):null;
`;
const inspectScript = `(()=>{${helpers}
 const text=main?.innerText||'';
 const login=!!document.querySelector('input[type="password"]')||/\\/(accounts\\/login|challenge|checkpoint)\\//.test(location.pathname);
 const restricted=/콘텐츠를 볼 수 없습니다|콘텐츠를 이용할 수 없습니다|This content isn't available|private account|비공개 계정/i.test(text);
 const account=Array.from(main?.querySelectorAll('a[href]')||[]).find(a=>/^\\/[A-Za-z0-9_.]+\\/?$/.test(a.getAttribute('href')||'')&&a.textContent?.trim()&&!/^(explore|accounts|reels|direct)$/.test(a.textContent.trim()));
 const uploader=account?.textContent?.trim().slice(0,100)||'';
 const id=location.pathname.split('/').filter(Boolean).pop();
 let caption='';
 if(uploader){captionSearch:for(const a of Array.from(main.querySelectorAll('a[href]')).filter(a=>a.getAttribute('href')===account.getAttribute('href')&&a.textContent?.trim()===uploader).slice(1,3)){let p=a.parentElement;for(let i=0;p&&i<5;i++,p=p.parentElement){if(p.querySelector('time')&&p.innerText.length<1200){const t=p.querySelector('time');const tail=p.innerText.split(t.innerText).slice(1).join(t.innerText).trim();if(tail.length>2){caption=tail.split('번역 보기')[0].trim().slice(0,160);break captionSearch;}}}}}
 const media=[];
 if(primary){if(primary.tagName==='VIDEO')media.push({kind:'video',url:primary.currentSrc||primary.src,duration:primary.duration,width:primary.videoWidth,height:primary.videoHeight,poster:primary.poster,encrypted:!!primary.mediaKeys});else if(primary.naturalWidth>=300&&primary.naturalHeight>=200)media.push({kind:'image',url:primary.currentSrc||primary.src,width:primary.naturalWidth,height:primary.naturalHeight});}
 return {title:caption||(uploader?uploader+' · '+id:id),uploader,media,hasNext:!!next,login,restricted,silent:/소리가 없는 동영상|video has no sound/i.test(text),signature:media.map(m=>m.url).join('|')};
})()`;
const advanceScript = `(()=>{${helpers}if(!next)return false;next.click();return true})()`;
const playScript = `(()=>{${helpers}if(primary?.tagName==='VIDEO'){primary.muted=true;void primary.play().catch(()=>{});}return true})()`;
module.exports = { inspectScript, advanceScript, playScript };
