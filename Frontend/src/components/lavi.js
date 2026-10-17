
const KEY='laviprina-herd-v1';
const $=s=>document.querySelector(s);
const today=()=>new Date().toISOString().slice(0,10);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function placeholder(a){
  const bg=a.species==='cow'?'#6d8fb0':'#c9a85c';
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="400" height="300" fill="${bg}"/><text x="200" y="175" font-size="110" text-anchor="middle" fill="#fff" font-family="sans-serif" font-weight="700">${esc((a.name||'?')[0].toUpperCase())}</text></svg>`;
  return 'data:image/svg+xml,'+encodeURIComponent(svg);
}
const seed=()=>[
 {id:'a1',name:'Daisy',tag:'KR-001',species:'cow',breed:'Friesian',sex:'Female',birth:'2020-03-14',weight:612,status:'Milking',pen:'Barn A',sire:'KR-B12',dam:'KR-044',vacc:'2026-06-10',vaccNext:'2026-12-10',milk:24.5,due:'',notes:'Top producer. Calm temperament.',photo:'',weights:[{d:'2026-04-01',w:598},{d:'2026-07-01',w:605},{d:'2026-09-30',w:612}]},
 {id:'a2',name:'Amani',tag:'KR-014',species:'cow',breed:'Jersey',sex:'Female',birth:'2021-08-02',weight:405,status:'Pregnant',pen:'Barn B',sire:'KR-B09',dam:'KR-022',vacc:'2026-05-20',vaccNext:'2026-10-15',milk:14,due:'2027-01-18',notes:'Due in January. Dry off in November.',photo:'',weights:[{d:'2026-06-01',w:390},{d:'2026-09-30',w:405}]},
 {id:'a3',name:'Zuri',tag:'KR-031',species:'cow',breed:'Ayrshire',sex:'Female',birth:'2022-11-21',weight:488,status:'Milking',pen:'Barn A',sire:'KR-B12',dam:'KR-017',vacc:'2026-06-10',vaccNext:'2026-12-10',milk:19.2,due:'',notes:'',photo:'',weights:[{d:'2026-09-30',w:488}]},
 {id:'s1',name:'Pendo',tag:'SH-102',species:'sheep',breed:'Dorper',sex:'Female',birth:'2023-02-09',weight:58,status:'Lactating',pen:'Paddock 2',sire:'SH-R04',dam:'SH-055',vacc:'2026-08-01',vaccNext:'2027-02-01',milk:'',due:'',notes:'Twin lambs born in August.',photo:'',weights:[{d:'2026-05-01',w:52},{d:'2026-09-30',w:58}]},
 {id:'s2',name:'Jabari',tag:'SH-R04',species:'sheep',breed:'Merino',sex:'Male',birth:'2021-05-30',weight:84,status:'Breeding',pen:'Paddock 1',sire:'',dam:'',vacc:'2026-08-01',vaccNext:'2027-02-01',milk:'',due:'',notes:'Main ram. Shear in March.',photo:'',weights:[{d:'2026-09-30',w:84}]},
 {id:'s3',name:'Tumaini',tag:'SH-118',species:'sheep',breed:'Red Maasai',sex:'Female',birth:'2025-06-12',weight:31,status:'Growing',pen:'Paddock 2',sire:'SH-R04',dam:'SH-055',vacc:'2026-08-01',vaccNext:'2026-10-01',milk:'',due:'',notes:'Check for worms.',photo:'',weights:[{d:'2026-09-30',w:31}]}
];
let herd;
try{herd=JSON.parse(localStorage.getItem(KEY))}catch(e){}
if(!Array.isArray(herd)||!herd.length)herd=seed();
function save(){try{localStorage.setItem(KEY,JSON.stringify(herd))}catch(e){toast('Could not save. Browser storage is full or blocked.')}}
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('on');setTimeout(()=>t.classList.remove('on'),2200)}

function age(b){
  if(!b)return '–';
  const d=new Date(b),n=new Date();
  let m=(n.getFullYear()-d.getFullYear())*12+n.getMonth()-d.getMonth();
  if(n.getDate()<d.getDate())m--;
  if(m<1)return 'Under 1 month';
  const y=Math.floor(m/12),r=m%12;
  return [y?y+' yr':'',r?r+' mo':''].filter(Boolean).join(' ');
}
const fmt=d=>d?new Date(d).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'}):'–';
const vaccDue=a=>a.vaccNext&&a.vaccNext<=new Date(Date.now()+14*864e5).toISOString().slice(0,10);
const label=a=>a.species==='cow'?'Dairy cow':'Sheep';

function render(){
  const q=$('#q').value.toLowerCase(),sp=$('#fSpecies').value,so=$('#sort').value;
  let list=herd.filter(a=>(!sp||a.species===sp)&&(`${a.name} ${a.tag} ${a.breed}`.toLowerCase().includes(q)));
  list.sort((a,b)=>so==='weight'?b.weight-a.weight:so==='age'?(a.birth<b.birth?-1:1):String(a[so]).localeCompare(b[so]));
  $('#grid').innerHTML=list.length?list.map(a=>`
   <button class="animal" data-id="${a.id}" aria-label="Open record for ${esc(a.name)}">
     <img src="${a.photo||placeholder(a)}" alt="${esc(a.name)}, ${esc(a.breed)} ${label(a).toLowerCase()}">
     <div class="meta"><h3>${esc(a.name)}</h3><small>Tag ${esc(a.tag)} · ${esc(a.breed)}</small><br>
     <span class="tag ${a.species}">${label(a)}</span> ${vaccDue(a)?'<span class="tag warn">Vaccine due</span>':''}</div>
   </button>`).join(''):'<div class="empty">No animals match. Clear the search or add a new animal.</div>';
  const cows=herd.filter(a=>a.species==='cow'),milk=cows.reduce((s,a)=>s+(+a.milk||0),0);
  $('#stats').innerHTML=`
   <div class="stat"><b>${herd.length}</b><span>Animals in total</span></div>
   <div class="stat"><b>${cows.length}</b><span>Dairy cows</span></div>
   <div class="stat"><b>${herd.length-cows.length}</b><span>Sheep</span></div>
   <div class="stat"><b>${milk.toFixed(0)} L</b><span>Daily milk (average)</span></div>
   <div class="stat alert"><b>${herd.filter(vaccDue).length}</b><span>Vaccinations due in 14 days</span></div>`;
}

function spark(ws){
  if(ws.length<2)return '<p style="color:var(--muted);margin:6px 0 0">Add another weight to see the trend.</p>';
  const v=ws.map(x=>x.w),mn=Math.min(...v),mx=Math.max(...v),W=300,H=60;
  const pts=ws.map((x,i)=>`${(i/(ws.length-1))*W},${H-6-((x.w-mn)/((mx-mn)||1))*(H-12)}`).join(' ');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="60" role="img" aria-label="Weight trend from ${v[0]} to ${v[v.length-1]} kilograms"><polyline points="${pts}" fill="none" stroke="var(--field)" stroke-width="3" stroke-linejoin="round"/></svg>`;
}

function openDetail(id){
  const a=herd.find(x=>x.id===id);if(!a)return;
  const dlg=$('#detail');
  const rows=[['Tag number',a.tag],['Type',label(a)],['Breed',a.breed],['Sex',a.sex],['Birthdate',fmt(a.birth)],['Age',age(a.birth)],['Current weight',a.weight+' kg'],['Status',a.status],['Pen or paddock',a.pen||'–'],['Sire',a.sire||'–'],['Dam',a.dam||'–'],['Last vaccination',fmt(a.vacc)],['Next vaccination',fmt(a.vaccNext)]];
  if(a.species==='cow')rows.push(['Average milk',a.milk?a.milk+' L/day':'–']);
  if(a.due)rows.push(['Expected birth',fmt(a.due)]);
  dlg.innerHTML=`
   <div class="dhead"><img src="${a.photo||placeholder(a)}" alt="${esc(a.name)}">
     <div><h2 id="dName">${esc(a.name)}</h2><div style="color:var(--muted)">Tag ${esc(a.tag)}</div></div>
     <button class="btn x" data-close>Close</button></div>
   <div class="dbody">
     <dl>${rows.map(r=>`<div><dt>${r[0]}</dt><dd>${esc(r[1])}</dd></div>`).join('')}</dl>
     ${a.notes?`<div class="notes"><b>Notes</b><br>${esc(a.notes)}</div>`:''}
     <h3 style="font-size:1.1rem">Weight history</h3>${spark(a.weights||[])}
     <div class="wlog"><input type="number" id="nw" min="1" step="0.1" placeholder="Weight (kg)" aria-label="New weight in kilograms"><input type="date" id="nd" value="${today()}" aria-label="Weighing date"><button class="btn" id="addW">Log weight</button></div>
   </div>
   <div class="dfoot"><button class="btn danger" id="del">Delete</button><button class="btn pri" style="padding:20px; border-radius: 8px; text-align: center; display: inline-block;" id="edit">Edit Record</button></div>`;
  dlg.showModal();
  $('#addW').onclick=()=>{
    const w=parseFloat($('#nw').value);if(!w)return toast('Enter a weight in kg');
    a.weights=(a.weights||[]).concat({d:$('#nd').value||today(),w}).sort((x,y)=>x.d<y.d?-1:1);
    a.weight=a.weights[a.weights.length-1].w;save();render();openDetail(id);toast('Weight logged');
  };
  $('#del').onclick=()=>{if(confirm(`Delete ${a.name} (${a.tag})? This cannot be undone.`)){herd=herd.filter(x=>x.id!==id);save();render();dlg.close();toast('Animal deleted')}};
  $('#edit').onclick=()=>{dlg.close();openForm(a)};
}

let editing=null,photoData='';
function openForm(a){
  editing=a||null;photoData=a?.photo||'';
  const f=$('#form');f.reset();
  $('#fTitle').textContent=a?'Edit '+a.name:'Add animal';
  if(a)[...f.elements].forEach(el=>{if(el.name&&el.type!=='file'&&a[el.name]!==undefined)el.value=a[el.name]});
  $('#formDlg').showModal();
}
$('#form').elements.photo.onchange=e=>{
  const file=e.target.files[0];if(!file)return;
  const img=new Image(),r=new FileReader();
  r.onload=()=>{img.onload=()=>{const s=Math.min(1,600/img.width),c=document.createElement('canvas');c.width=img.width*s;c.height=img.height*s;c.getContext('2d').drawImage(img,0,0,c.width,c.height);photoData=c.toDataURL('image/jpeg',.8)};img.src=r.result};
  r.readAsDataURL(file);
};
$('#form').onsubmit=e=>{
  e.preventDefault();
  const d=Object.fromEntries(new FormData(e.target));delete d.photo;
  d.weight=parseFloat(d.weight);d.photo=photoData;
  if(editing){
    const w=editing.weights||[];
    if(d.weight!==editing.weight)w.push({d:today(),w:d.weight});
    Object.assign(editing,d,{weights:w});
  }else herd.push({...d,id:'a'+Date.now(),weights:[{d:today(),w:d.weight}]});
  save();render();$('#formDlg').close();toast(editing?'Changes saved':'Animal added');
};

document.addEventListener('click',e=>{
  const card=e.target.closest('.animal');if(card)openDetail(card.dataset.id);
  if(e.target.matches('[data-close]'))e.target.closest('dialog').close();
  if(e.target.tagName==='DIALOG')e.target.close();
});
$('#addBtn').onclick=()=>openForm();
['#q','#fSpecies','#sort'].forEach(s=>$(s).addEventListener('input',render));
$('#exp').onclick=()=>{
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(herd,null,2)],{type:'application/json'}));
  a.download='herd-backup-'+today()+'.json';a.click();
};
$('#imp').onclick=()=>$('#impFile').click();
$('#impFile').onchange=e=>{
  const r=new FileReader();
  r.onload=()=>{try{const d=JSON.parse(r.result);if(!Array.isArray(d))throw 0;herd=d;save();render();toast('Backup imported')}catch(x){toast('That file is not a valid herd backup')}};
  r.readAsText(e.target.files[0]);
};
render();
