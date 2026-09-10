const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../dataset_ui/index.html'),'utf8');
function setup(storage=new Map()){
 class Element{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.textContent='';this.value='';this.classList={toggle(){}};}
  append(...nodes){this.children.push(...nodes)}
  replaceChildren(...nodes){this.children=nodes;this.textContent=''}
  scrollIntoView(){this.scrolled=true}
  focus(){this.focused=true}
  get childElementCount(){return this.children.length}
 }
 const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
 const calls=[];
 const ctx=vm.createContext({localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},document:{getElementById:get,createElement:tag=>new Element(tag)},fetch:()=>new Promise(()=>{}),URLSearchParams,console,showAlignment:(root,work)=>{calls.push({root,work});get('alignmentPanel').replaceChildren(new Element('section'));}});
 vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],ctx);
 const onclick=html.match(/onclick="([^"]*)">展开录音与乐谱对齐/)[1];
 return {get,calls,run:s=>vm.runInContext(s,ctx),click:()=>vm.runInContext(onclick,ctx)};
}
const scan="renderScan({root:'/data',works:[{id:'piece-a',audio:[],scores:[],eligible:false},{id:'piece-b',audio:[],scores:[],eligible:false}],warnings:[],group_count:0,eligible_count:0})";
function descendants(node){return [node,...node.children.flatMap(descendants)]}
test('without a selected work the button displays a chooser and opens the chosen work',()=>{
 const s=setup();s.run(scan);s.click();
 const select=descendants(s.get('alignmentPanel')).find(n=>n.tagName==='select');
 assert.ok(select,'click must display a work selector instead of scrolling to an empty panel');
 select.value='piece-b';select.onchange();
 assert.equal(s.calls.at(-1).work,'piece-b');assert.equal(s.get('selected').textContent,'piece-b');
});
test('before scanning the button gives visible instructions',()=>{
 const s=setup();s.click();assert.match(descendants(s.get('alignmentPanel')).map(n=>n.textContent).join(' '),/扫描/);
});
test('selected work navigation preserves the existing editor and rescan clears selection',()=>{
 const s=setup();s.run(scan);s.run('showFiles(inventory.works[0])');const panel=s.get('alignmentPanel').children[0];
 s.click();assert.equal(s.get('alignmentPanel').children[0],panel);assert.equal(s.calls.length,1);
 s.run(scan);s.click();assert.ok(descendants(s.get('alignmentPanel')).some(n=>n.tagName==='select'));
});
test('alignment workspace is directly below its entry button, before the file list',()=>{
 assert.match(html,/onclick="openAlignment\(\)">[^<]*<\/button>\s*<div id="alignmentPanel"[^>]*><\/div>\s*<div id="files">/);
 assert.equal((html.match(/id="alignmentPanel"/g)||[]).length,1);
});

test('refresh restores cached inventory and selected work without a download or scan',()=>{
 const storage=new Map(),first=setup(storage);first.run(scan);first.run('showFiles(inventory.works[1])');
 const next=setup(storage);assert.equal(next.run('restoreWorkspace()'),true);
 assert.equal(next.get('root').value,'/data');assert.equal(next.get('selected').textContent,'piece-b');
 assert.equal(next.calls.at(-1).work,'piece-b');
 assert.match(next.get('message').textContent,/恢复/);
 assert.ok(![...storage.values()].join('').includes('cloudSecret'));
});
test('changing the dataset clears its saved selection',()=>{
 const storage=new Map(),first=setup(storage);first.run(scan);first.run('clearInventory()');
 const next=setup(storage);assert.equal(next.run('restoreWorkspace()'),false);
});
