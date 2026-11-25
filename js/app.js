const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const state={page:'home',tab:'',activeEmail:null,serverAuthenticated:false,selectedCaseId:null,selectedCompanyRuc:null,editingCaseId:null,matrixPage:0,expenseEvaluation:null,pendingExpenseFiles:[],empresa:{razon:'',ruc:'',tipo:'Persona Jurídica',tamano:'Pequeña Empresa',fecha:'',domicilio:'',actividad:''},fin:{ingresos:0,costos:0,gastos:0},cases:[],companies:[],receipts:[],profile:{name:'',email:''}};
const SUNAT_RUC_URL='https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias';
const SUNAT_LAW_URLS={
  lir37:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=1',
  lir37Reasonableness:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=12',
  lir37Interest:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=2',
  lir37General:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=8',
  lir37Representation:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=9',
  lir37Travel:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=9',
  lir37Vehicles:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=10',
  lir37Donations:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=11',
  lir44:'https://www.sunat.gob.pe/legislacion/renta/ley/capvi.pdf#page=13',
  lir57:'https://www.sunat.gob.pe/legislacion/renta/ley/capviii.pdf#page=1',
  paymentMethods3:'https://www.sunat.gob.pe/legislacion/itf/ds150_07.pdf#page=3',
  paymentMethods4:'https://www.sunat.gob.pe/legislacion/itf/ds150_07.pdf#page=6',
  paymentMethods8:'https://www.sunat.gob.pe/legislacion/itf/ds150_07.pdf#page=9'
};
const RUC_LOOKUP_TARGETS={
  companyRuc:{name:'companyName',activity:'companyActivity',status:'companyRucStatus'},
  caseCompanyRuc:{name:'caseCompanyName',activity:'caseCompanyActivity',status:'caseCompanyStatus'},
  caseProviderRuc:{name:'caseProvider',status:'caseRucStatus'},
  receiptReceiverRuc:{name:'receiptReceiverName'},
  receiptProviderRuc:{name:'receiptProviderName'}
};

// Acceso visual: pestañas y visibilidad de contraseña.
function showAuthPanel(which){
  const login=which==='login';
  $('#loginPanel').classList.toggle('hidden',!login);
  $('#registerPanel').classList.toggle('hidden',login);
  $('#authTabLogin').classList.toggle('active',login);
  $('#authTabRegister').classList.toggle('active',!login);
  $('#authTabLogin').setAttribute('aria-selected',String(login));
  $('#authTabRegister').setAttribute('aria-selected',String(!login));
}
$('#authTabLogin')?.addEventListener('click',()=>showAuthPanel('login'));
$('#authTabRegister')?.addEventListener('click',()=>showAuthPanel('register'));
$$('[data-toggle-password]').forEach(btn=>btn.addEventListener('click',()=>{
  const input=document.getElementById(btn.dataset.togglePassword);
  if(!input)return;
  input.type=input.type==='password'?'text':'password';
  btn.setAttribute('aria-label',input.type==='password'?'Mostrar contraseña':'Ocultar contraseña');
}));
$('#forgotPassword')?.addEventListener('click',()=>{
  toast('Para recuperar el acceso, solicita el restablecimiento al administrador de esta instalación.');
});

const ACCOUNT_KEY='ta_accounts_v2';
let workspaceSaveChain=Promise.resolve();
let workspaceRevision=0;
async function apiRequest(url,options={}){
  const response=await fetch(url,{credentials:'same-origin',...options});
  let data={};
  try{data=await response.json()}catch{}
  if(!response.ok)throw new Error(data.error||`Error del servidor (${response.status}).`);
  return data;
}
function accounts(){try{return JSON.parse(localStorage.getItem(ACCOUNT_KEY)||'[]')}catch{return []}}
function workspaceKey(email){return 'ta_workspace_'+btoa(unescape(encodeURIComponent(email.trim().toLowerCase()))).replace(/[^a-zA-Z0-9]/g,'')}
function saveWorkspace(){
  if(!state.activeEmail)return Promise.resolve();
  const snapshot={cases:state.cases,companies:state.companies,receipts:state.receipts,profile:state.profile,empresa:state.empresa,fin:state.fin,updatedAt:new Date().toISOString()};
  if(!state.serverAuthenticated){
    localStorage.setItem(workspaceKey(state.activeEmail),JSON.stringify(snapshot));
    return Promise.resolve(true);
  }
  const revision=++workspaceRevision;
  workspaceSaveChain=workspaceSaveChain.catch(()=>{}).then(async()=>{
    const result=await apiRequest('/api/workspace',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(snapshot)});
    if(revision===workspaceRevision&&Array.isArray(result.cases))state.cases=result.cases;
    return true;
  }).catch(error=>{
    if(revision===workspaceRevision)toast(`No se guardó en la base de datos: ${error.message}`);
    return false;
  });
  return workspaceSaveChain;
}
function loadWorkspace(user,serverData=null){
  state.activeEmail=user.email;
  state.profile={name:user.name,email:user.email};
  let raw=localStorage.getItem(workspaceKey(user.email)),localData={};
  try{localData=raw?JSON.parse(raw):{}}catch{localData={}}
  const useServer=serverData&&(
    (serverData.cases||[]).length||(serverData.receipts||[]).length||
    (serverData.companies||[]).length||Object.keys(serverData.empresa||{}).length||Object.keys(serverData.fin||{}).length
  );
  const data=useServer?serverData:localData;
  state.cases=data.cases||[];
  state.companies=data.companies||[];
  state.receipts=data.receipts||[];
  state.profile={...state.profile,...(data.profile||{})};
  state.empresa={...state.empresa,...(data.empresa||{})};
  state.fin={...state.fin,...(data.fin||{})};
  return {hasLocalData:Boolean(raw),serverHasData:Boolean(useServer)};
}
function saveCases(){return saveWorkspace()}
function saveReceipts(){return saveWorkspace()}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

function toast(m){let t=$('#toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3000)}
function money(n){return new Intl.NumberFormat('es-PE',{style:'currency',currency:'PEN',maximumFractionDigits:0}).format(n||0)}
async function passwordHash(password){const bytes=new TextEncoder().encode(password);if(window.crypto?.subtle){const digest=await crypto.subtle.digest('SHA-256',bytes);return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('')}return btoa(unescape(encodeURIComponent(password)))}
function shortUserName(name){return (String(name||'Usuario').trim().split(/\s+/)[0]||'Usuario')}
async function enterWorkspace(user){
  state.serverAuthenticated=true;
  const localState=loadWorkspace(user);
  let serverData;
  try{serverData=await apiRequest('/api/workspace')}catch(error){
    state.serverAuthenticated=false;
    toast(`No se pudo cargar el historial de la base de datos: ${error.message}`);
    return;
  }
  const loaded=loadWorkspace(user,serverData);
  if(!loaded.serverHasData&&localState.hasLocalData){
    if(await saveWorkspace())localStorage.removeItem(workspaceKey(user.email));
  }else if(loaded.serverHasData&&localState.hasLocalData){
    localStorage.removeItem(workspaceKey(user.email));
  }
  const shortName=shortUserName(user.name);
  $('#topShortName').textContent=shortName;
  $('#topAvatar').textContent=shortName.charAt(0).toUpperCase();
  $('#menuUserName').textContent=user.name;
  $('#menuUserEmail').textContent=user.email;
  $('#auth').classList.add('hidden');
  $('#app').classList.remove('hidden');
  render();
}
$('#loginBtn').onclick=async()=>{
  const email=$('#loginEmail').value.trim().toLowerCase(),password=$('#loginPassword').value;
  if(!email||!password){toast('Ingresa tu correo y contraseña.');return}
  try{
    const result=await apiRequest('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
    enterWorkspace(result.user);
  }catch(error){
    const legacyUser=accounts().find(account=>account.email===email);
    if(legacyUser&&await passwordHash(password)===legacyUser.passwordHash){
      try{
        const migrated=await apiRequest('/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:legacyUser.name,email,password})});
          localStorage.setItem(ACCOUNT_KEY,JSON.stringify(accounts().filter(account=>account.email!==email)));
          enterWorkspace(migrated.user);
      }catch(migrationError){toast(migrationError.message)}
      return;
    }
    toast(error.message);
  }
};

$('#registerBtn').onclick=async()=>{
  const name=$('#regName').value.trim(),email=$('#regEmail').value.trim().toLowerCase(),password=$('#regPassword').value;
  if(name.length<2||!/^\S+@\S+\.\S+$/.test(email)||password.length<6){toast('Revisa tu nombre, correo y contraseña de al menos 6 caracteres.');return}
  try{
    const result=await apiRequest('/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,password})});
    $('#regName').value='';$('#regEmail').value='';$('#regPassword').value='';
    await enterWorkspace(result.user);
    toast('¡Cuenta creada! Tu historial se guarda en la base de datos.');
  }catch(error){toast(error.message)}
};
async function closeWorkspace(){
  await saveWorkspace();
  try{await apiRequest('/api/logout',{method:'POST'})}catch(error){toast(`No se pudo cerrar la sesión del servidor: ${error.message}`)}
  state.activeEmail=null;
  state.serverAuthenticated=false;
  $('#app').classList.add('hidden');
  $('#auth').classList.remove('hidden');
  $('#loginPassword').value='';
  $('#userMenu').classList.add('hidden');
  $('#userMenuToggle').setAttribute('aria-expanded','false');
  showAuthPanel('login');
}
$('#menuLogoutBtn').onclick=closeWorkspace;
$('#userMenuToggle').onclick=()=>{
  const menu=$('#userMenu'),open=menu.classList.contains('hidden');
  menu.classList.toggle('hidden',!open);
  $('#userMenuToggle').setAttribute('aria-expanded',String(open));
};
document.addEventListener('click',e=>{
  if(!e.target.closest('.user-menu-wrap')){
    $('#userMenu')?.classList.add('hidden');
    $('#userMenuToggle')?.setAttribute('aria-expanded','false');
  }
  const closeDetails=e.target.closest('[data-close-matrix-detail]');
  if(closeDetails)closeDetails.closest('details')?.removeAttribute('open');
});
$('#noticeBtn').onclick=()=>toast('No tienes notificaciones nuevas.');
$('#sideNav').onclick=e=>{let b=e.target.closest('[data-page]');if(b)go(b.dataset.page)};
function go(page){const allowed=['home','empresas','nuevo','comprobantes','masiva','matrices','casos','guia','perfil'];const next=allowed.includes(page)?page:'home';if(next==='nuevo'&&state.page!=='nuevo')state.pendingExpenseFiles=[];if(next!=='nuevo')state.editingCaseId=null;state.page=next;state.tab='';state.selectedCaseId=null;state.selectedCompanyRuc=null;state.expenseEvaluation=null;$$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.page===next));render();window.scrollTo(0,0)}
function hero(title,sub){return `<section class="hero"><span class="eyebrow">TRIBUANÁLISIS · RENTAS EMPRESARIALES</span><h1>${title}</h1><p>${sub}</p></section>`}
function tabs(items,active){return `<div class="tabs">${items.map(x=>`<button class="tab ${active===x[0]?'active':''}" data-tab="${x[0]}">${x[1]}</button>`).join('')}</div>`}
function panel(title,body){return `<section class="panel"><h2>${title}</h2>${body}</section>`}
function field(label,id,value,type='text'){return `<label class="field">${label}<input id="${id}" type="${type}" value="${esc(value??'')}"></label>`}
function sunatRucField(label,id){return `<div class="field ruc-field"><label for="${id}">${label}</label><div class="ruc-field-controls"><input id="${id}" data-ruc-input type="text" inputmode="numeric" maxlength="11" autocomplete="off" placeholder="11 dígitos"><button type="button" class="btn" data-ruc-search="${id}">Buscar datos</button></div><small><span class="ruc-lookup-status" data-ruc-status="${id}" role="status" aria-live="polite">Escribe el RUC y presiona Enter o Buscar datos.</span> <a href="${SUNAT_RUC_URL}" target="_blank" rel="noopener noreferrer">Consulta manual en SUNAT ↗</a></small><dl class="ruc-lookup-details" data-ruc-details="${id}" hidden><div><dt>RUC</dt><dd data-ruc-value="${id}-ruc">No disponible</dd></div><div><dt>Razón social</dt><dd data-ruc-value="${id}-name">No disponible</dd></div><div><dt>Actividad principal</dt><dd data-ruc-value="${id}-activity">No disponible en la respuesta</dd></div><div><dt>Actividad secundaria 1</dt><dd data-ruc-value="${id}-activity1">No disponible en la respuesta</dd></div><div><dt>Actividad secundaria 2</dt><dd data-ruc-value="${id}-activity2">No disponible en la respuesta</dd></div><div><dt>Código CIIU</dt><dd data-ruc-value="${id}-ciiu">No disponible en la respuesta</dd></div><div><dt>Estado y condición</dt><dd data-ruc-value="${id}-status">No disponible</dd></div></dl></div>`}
function rucLookupData(id){
  const details=$(`[data-ruc-details="${id}"]`);
  if(!details?.dataset.lookup)return {};
  try{return JSON.parse(details.dataset.lookup)}
  catch(error){console.error('No se pudieron leer los datos de consulta RUC conservados en el formulario.',error);return {}}
}
function selectField(label,id,opts,value){return `<label class="field">${label}<select id="${id}">${opts.map(o=>`<option ${o===value?'selected':''}>${o}</option>`).join('')}</select></label>`}
function choiceField(label,id,opts){return `<label class="field">${label}<select id="${id}"><option value="">Selecciona una opción</option>${opts.map(([value,text])=>`<option value="${esc(value)}">${esc(text)}</option>`).join('')}</select></label>`}
function isValidRuc(value){
  const ruc=String(value??'').trim();
  if(!/^\d{11}$/.test(ruc))return false;
  const weights=[5,4,3,2,7,6,5,4,3,2];
  const sum=[...ruc.slice(0,10)].reduce((total,digit,index)=>total+Number(digit)*weights[index],0);
  const check=11-(sum%11);
  const expected=check===10?0:check===11?1:check;
  return Number(ruc[10])===expected;
}
function setLookupTarget(id,value){
  if(!id||value===undefined||value===null||value==='')return;
  const target=$('#'+id);
  if(!target)return;
  const previous=target.value;
  if(target instanceof HTMLSelectElement){
    let option=[...target.options].find(item=>item.value===value);
    if(!option){option=new Option(value,value);target.add(option)}
    target.value=value;
  }else target.value=value;
  if(target.value!==previous)target.dispatchEvent(new Event('input',{bubbles:true}));
}
async function lookupRuc(input){
  const ruc=input.value.trim(),status=$(`[data-ruc-status="${input.id}"]`),button=$(`[data-ruc-search="${input.id}"]`);
  if(!isValidRuc(ruc)){status.textContent='Verifica que el RUC tenga 11 dígitos y sea válido.';return}
  const targets=RUC_LOOKUP_TARGETS[input.id];
  if(!targets){status.textContent='Este campo no tiene una consulta automática configurada.';return}
  const requestId=String(Number(input.dataset.lookupRequest||0)+1);
  input.dataset.lookupRequest=requestId;
  status.textContent='Consultando los datos del RUC...';
  button.disabled=true;
  try{
    const response=await fetch(`/api/ruc/${encodeURIComponent(ruc)}`);
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'No se pudo completar la consulta.');
    if(input.dataset.lookupRequest!==requestId||input.value.trim()!==ruc)return;
    setLookupTarget(targets.name,data.razonSocial);
    setLookupTarget(targets.activity,data.actividadEconomicaPrincipal||data.actividadEconomica);
    const condition=[data.estado,data.condicion].filter(Boolean).join(' · ');
    setLookupTarget(targets.status,condition);
    const details=$(`[data-ruc-details="${input.id}"]`);
    if(details){
      details.dataset.lookup=JSON.stringify(data);
      details.hidden=false;
      const values={
        ruc:data.ruc||ruc,
        name:data.razonSocial||'No disponible en la respuesta',
        activity:data.actividadEconomicaPrincipal||data.actividadEconomica||'No disponible en la respuesta',
        activity1:data.actividadEconomicaSecundaria1||'No disponible en la respuesta',
        activity2:data.actividadEconomicaSecundaria2||'No disponible en la respuesta',
        ciiu:data.codigoCIIU||'No disponible en la respuesta',
        status:[data.estado,data.condicion].filter(Boolean).join(' · ')||'No disponible en la respuesta'
      };
      Object.entries(values).forEach(([key,value])=>{
        const output=$(`[data-ruc-value="${input.id}-${key}"]`);
        if(output)output.textContent=value;
      });
    }
    input.dataset.lastLookupRuc=ruc;
    status.textContent=`Datos del RUC agregados al formulario${condition?` · ${condition}`:''}.`;
  }catch(error){
    if(input.dataset.lookupRequest===requestId){
      status.textContent=error instanceof Error?error.message:'No se pudo completar la consulta RUC.';
    }
  }finally{
    if(input.dataset.lookupRequest===requestId)button.disabled=false;
  }
}
function clearStaleLookup(input){
  const changed=Boolean(input.dataset.lastLookupRuc&&input.dataset.lastLookupRuc!==input.value.trim());
  const button=$(`[data-ruc-search="${input.id}"]`);
  const pending=Boolean(button?.disabled);
  if(!changed&&!pending)return;
  if(pending){
    input.dataset.lookupRequest=String(Number(input.dataset.lookupRequest||0)+1);
    button.disabled=false;
  }
  if(changed){
    const targets=RUC_LOOKUP_TARGETS[input.id]||{};
    [targets.name,targets.activity,targets.status].forEach(id=>{
      const target=id?$('#'+id):null;
      if(!target)return;
      if(target instanceof HTMLSelectElement)target.selectedIndex=0;
      else target.value='';
    });
    const details=$(`[data-ruc-details="${input.id}"]`);
    if(details){details.hidden=true;delete details.dataset.lookup}
    delete input.dataset.lastLookupRuc;
  }
  const status=$(`[data-ruc-status="${input.id}"]`);
  if(status)status.textContent='RUC modificado. Presiona Enter para actualizar los datos.';
}
async function evaluateExpense(expense){
  return apiRequest('/api/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(expense)});
}
function caseEvaluation(caseItem){
  return caseItem.evaluation||{
    status:'condicionado',
    label:'Condicionado',
    summary:'Este registro histórico no contiene evidencia suficiente para emitir una evaluación automática.',
    negative:[],
    missing:['Adjuntar y revisar la documentación del registro histórico.'],
    criteria:[],
    evaluatedAt:null,
    version:2,
    deductibleAmount:null,
    nonDeductibleAmount:null
  };
}
function evaluationBadge(caseItem){
  const evaluation=caseEvaluation(caseItem),className=evaluation.status==='deducible'?'deductible':evaluation.status==='no_deducible'?'nondeductible':evaluation.status==='limitado'?'limited':'conditional';
  return `<span class="evaluation-badge ${className}">${esc(evaluation.label||'Condicionado')}</span>`;
}
let evaluationTimer=null;
let evaluationRequest=0;
function invalidateExpenseEvaluation(){
  if(state.page!=='nuevo')return;
  state.expenseEvaluation=null;
  if($('#saveManualCase'))$('#saveManualCase').disabled=true;
  if($('#evaluationPreview'))$('#evaluationPreview').innerHTML='<div class="notice">Evaluando automáticamente los datos disponibles…</div>';
  clearTimeout(evaluationTimer);
  evaluationTimer=setTimeout(refreshAutomaticEvaluation,350);
}
function expenseFormData(){
  const lookup=rucLookupData('caseCompanyRuc');
  return {
    empresaRuc:$('#caseCompanyRuc')?.value.trim()||'',empresa:$('#caseCompanyName')?.value.trim()||'',
    empresaActividad:$('#caseCompanyActivity')?.value.trim()||'',empresaRucStatus:$('#caseCompanyStatus')?.value.trim()||'',
    empresaActividadSecundaria1:lookup.actividadEconomicaSecundaria1||'',
    empresaActividadSecundaria2:lookup.actividadEconomicaSecundaria2||'',
    empresaCodigoCIIU:lookup.codigoCIIU||'',
    empresaRucFuente:lookup.source||'',empresaRucFechaConsulta:lookup.consultedAt||'',
    tipoOperacion:$('#caseType').value,tipoComprobante:$('#caseVoucherType').value,fecha:$('#caseDate').value,
    fechaServicio:$('#caseServiceDate').value,
    proveedorRuc:$('#caseProviderRuc').value.trim(),proveedor:$('#caseProvider').value.trim(),
    proveedorRucSunatStatus:$('#caseRucStatus')?.value||'',rucReceptor:$('#caseReceiverRuc').value.trim(),
    numero:$('#caseNumber').value.trim(),concepto:$('#caseConcept').value.trim(),
    moneda:$('#caseCurrency').value,monto:Number($('#caseAmount').value),
    baseImponible:Number($('#caseTaxBase')?.value||0),igv:Number($('#caseIGV')?.value||0),
    importeReferencia:Number($('#caseReferenceAmount').value),
    ingresosNetosAnuales:Number($('#caseGrossIncome').value),
    medioPago:$('#casePaymentMethod').value.trim(),referenciaPago:$('#casePaymentReference').value.trim(),
    descripcion:$('#caseDesc').value.trim(),evidencia:$('#caseEvidence').value.trim(),
    documentos:state.pendingExpenseFiles.map(item=>({
      name:item.name,size:item.size,contentType:item.contentType,
      datosExtraidos:item.datosExtraidos||{},warning:item.warning||''
    }))
  };
}
function expenseEvaluationHtml(evaluation){
  const className=evaluation.status==='deducible'?'deductible':evaluation.status==='no_deducible'?'nondeductible':evaluation.status==='limitado'?'limited':'conditional';
  const formatAmount=value=>value===null||value===undefined?'Por determinar':money(value);
  const criteria=(evaluation.criteria||[]).map(item=>`<article><div><b>${esc(item.label)}</b><span class="criterion-status ${esc(item.status)}">${item.status==='cumple'?'Indicio favorable':item.status==='no_cumple'?'No cumple':item.status==='no_aplica'?'No aplica':'Pendiente'}</span><p>${esc(item.detail)}</p><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.reference)} ↗</a></div></article>`).join('');
  const observations=[...(evaluation.missing||[]),...(evaluation.observations||[]),...(evaluation.negative||[])];
  const followup=evaluation.missing?.length
    ?`<p class="analysis-followup">${evaluation.missing.length} requisito(s) esencial(es) pendiente(s). <span>Abre el fundamento para ver el detalle.</span></p>`
    :evaluation.negative?.length
      ?'<p class="analysis-followup">Se identificó un posible incumplimiento; revisa el detalle normativo.</p>'
      :evaluation.observations?.length
        ?'<p class="analysis-followup">Hay observaciones complementarias que no bloquean la clasificación.</p>':'';
  return `<section class="expense-evaluation ${className}" aria-live="polite"><div class="evaluation-heading"><span class="guide-kicker">ANÁLISIS AUTOMÁTICO</span><strong>${esc(evaluation.label)}</strong><p>${esc(evaluation.summary)}</p></div><div class="stats"><div class="stat"><small>Importe deducible</small><strong>${formatAmount(evaluation.deductibleAmount)}</strong></div><div class="stat"><small>Importe no deducible / exceso</small><strong>${formatAmount(evaluation.nonDeductibleAmount)}</strong></div></div>${followup}<details class="criteria-disclosure"><summary>Fundamento normativo y criterios (${(evaluation.criteria||[]).length})</summary><div class="evaluation-criteria">${criteria}</div>${observations.length?`<ul class="criteria-observations">${observations.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:''}</details><p class="footer-note">El análisis es preliminar. La consulta del RUC/comprobante ante SUNAT es independiente y no prueba por sí sola la realidad ni deducibilidad del gasto.</p></section>`;
}
async function refreshAutomaticEvaluation(){
  if(state.page!=='nuevo'||!$('#evaluationPreview'))return;
  const draft=expenseFormData(),requestId=++evaluationRequest;
  const hasInput=[draft.empresaRuc,draft.proveedorRuc,draft.concepto,draft.descripcion,draft.monto].some(value=>String(value||'').trim());
  if(!hasInput){
    state.expenseEvaluation=null;
    $('#evaluationPreview').innerHTML='<div class="analysis-empty">Completa los datos de la operación para que el sistema determine su clasificación. La normativa aplicada se mostrará con el resultado.</div>';
    $('#saveManualCase').disabled=true;
    return;
  }
  try{
    const result=await evaluateExpense(draft);
    if(requestId!==evaluationRequest||state.page!=='nuevo')return;
    state.expenseEvaluation={snapshot:JSON.stringify(draft),draft,result};
    $('#evaluationPreview').innerHTML=expenseEvaluationHtml(result);
    const required=[draft.empresaRuc,draft.empresa,draft.fecha,draft.proveedorRuc,draft.proveedor,draft.numero,draft.concepto];
    $('#saveManualCase').disabled=required.some(value=>!String(value||'').trim())||!(draft.monto>0);
  }catch(error){
    if(requestId!==evaluationRequest)return;
    state.expenseEvaluation=null;
    $('#evaluationPreview').innerHTML=`<div class="notice">No se pudo completar la evaluación automática: ${esc(error.message)}</div>`;
    $('#saveManualCase').disabled=true;
  }
}
function home(){
  const pending=state.cases.filter(item=>caseEvaluation(item).status==='condicionado').length;
  return `<section class="dashboard-hero">
    <div class="hero-copy">
      <span class="eyebrow">TRIBUANÁLISIS · RENTAS EMPRESARIALES</span>
      <h1>Analiza con criterio. Decide con sustento.</h1>
      <p class="hero-description">Evalúa gastos empresariales, reúne su evidencia y consulta la normativa tributaria aplicable.</p>
      <button class="btn primary dashboard-cta" data-go="nuevo">＋ Iniciar análisis de gasto</button>
    </div>
    <div class="hero-photo" role="img" aria-label="Libros de legislación, balanza, calculadora y documentos contables"></div>
  </section>
  <section class="dashboard-overview" aria-label="Resumen">
    <div class="dashboard-stat wine"><span class="stat-icon">▤</span><div><small>Análisis guardados</small><strong>${state.cases.length}</strong></div></div>
    <div class="dashboard-stat blue"><span class="stat-icon">◷</span><div><small>Pendientes de revisión</small><strong>${pending}</strong></div></div>
    <div class="dashboard-stat teal"><span class="stat-icon">▣</span><div><small>Comprobantes registrados</small><strong>${state.receipts.length}</strong></div></div>
  </section>
  <section class="dashboard-actions" aria-label="Accesos principales">
    <button class="dashboard-action-card" data-go="nuevo"><span class="dashboard-action-icon">＋</span><span><strong>Analizar un gasto</strong><small>Registra la operación y evalúa su sustento.</small></span><b>→</b></button>
    <button class="dashboard-action-card" data-go="comprobantes"><span class="dashboard-action-icon">▤</span><span><strong>Revisar comprobantes</strong><small>Registra los datos del documento y su RUC.</small></span><b>→</b></button>
    <button class="dashboard-action-card" data-go="guia"><span class="dashboard-action-icon">§</span><span><strong>Consultar normativa</strong><small>Revisa los principios y su fundamento legal.</small></span><b>→</b></button>
    <button class="dashboard-action-card" data-go="casos"><span class="dashboard-action-icon">▱</span><span><strong>Ver historial</strong><small>Consulta los análisis que has guardado.</small></span><b>→</b></button>
  </section>`;
}
function criterionSummary(caseItem,key){
  const criteria=caseEvaluation(caseItem).criteria.filter(item=>item.key===key);
  if(!criteria.length)return 'Pendiente';
  return [...new Set(criteria.map(item=>item.status==='cumple'?'Cumple':item.status==='no_cumple'?'No cumple':item.status==='no_aplica'?'No aplica':'Pendiente'))].join(' / ');
}
function matrixValues(caseItem){
  const evaluation=caseEvaluation(caseItem);
  return [
    caseItem.fecha||'—',caseItem.numero||'—',
    `${caseItem.proveedor||'—'} / ${caseItem.proveedorRuc||'—'}`,
    caseItem.descripcionDetalladaGasto||caseItem.concepto||'—',
    caseItem.empresaActividad||'—',Number(caseItem.monto||0),
    caseItem.validacionComprobante||'Pendiente de consulta oficial SUNAT',
    criterionSummary(caseItem,'causalidad'),criterionSummary(caseItem,'fehaciencia'),
    criterionSummary(caseItem,'razonabilidad'),criterionSummary(caseItem,'generalidad'),
    evaluation.label||'Condicionado',
    evaluation.deductibleAmount===null||evaluation.deductibleAmount===undefined?'Por determinar':Number(evaluation.deductibleAmount),
    evaluation.nonDeductibleAmount===null||evaluation.nonDeductibleAmount===undefined?'Por determinar':Number(evaluation.nonDeductibleAmount),
    (evaluation.legalBasis||[]).join('; '),
    [...(caseItem.importObservations||[]),...(evaluation.negative||[]),...(evaluation.missing||[]),...(evaluation.observations||[])].join(' | ')||evaluation.summary||'',
    caseItem.evidencia||'—',
    caseItem.loteExcel?.nombre||'—',
    caseItem.loteExcel?.fila||'—'
  ];
}
const MATRIX_HEADERS=['Fecha','Comprobante','Proveedor y RUC','Descripción detallada del gasto','Actividad económica relacionada','Importe','Validación SUNAT','Causalidad','Fehaciencia','Proporcionalidad','Generalidad','Clasificación','Importe deducible','Importe no deducible','Fundamento normativo','Observaciones','Sustento adicional declarado','Archivo Excel','Fila Excel'];
function caseTable(arr,actions=true){
  const rows=arr.map(item=>{
    const evaluation=caseEvaluation(item);
    const value=value=>value===null||value===undefined?'Por determinar':money(value);
    const fullDate=String(item.fecha||'—');
    const shortDate=/^\d{4}-\d{2}-\d{2}$/.test(fullDate)?`${fullDate.slice(8,10)}/${fullDate.slice(5,7)}/${fullDate.slice(2,4)}`:fullDate;
    const identityNeedsReview=(evaluation.criteria||[]).some(criterion=>
      ['Identificación de la empresa','Identificación del proveedor','RUC receptor declarado'].includes(criterion.label)&&criterion.status==='pendiente'
    );
    const observations=[...(item.importObservations||[]),...(evaluation.negative||[]),...(evaluation.missing||[]),...(evaluation.observations||[])];
    const legalBasis=(evaluation.criteria||[]).map(criterion=>`<li><b>${esc(criterion.label)}:</b> ${esc(criterion.detail)} <a href="${esc(criterion.url)}" target="_blank" rel="noopener noreferrer">${esc(criterion.reference)} ↗</a></li>`).join('');
    const details=`<details class="matrix-cell-details"><summary>Ver detalle</summary><div><div class="matrix-detail-heading"><b>Evaluación y sustento</b><button type="button" class="btn" data-close-matrix-detail aria-label="Cerrar detalle">Cerrar</button></div><p><b>Validación SUNAT:</b> ${esc(item.validacionComprobante||'Pendiente')}</p><p><b>Actividad empresarial:</b> ${esc(item.empresaActividad||'No disponible')}</p><p><b>Tipo detectado:</b> ${esc(evaluation.expenseCategory||'Gasto empresarial')}</p><p><b>Fundamento normativo:</b> ${esc((evaluation.legalBasis||[]).join('; ')||'Revisar normativa aplicable al caso.')}</p><ul>${legalBasis}</ul>${item.evidencia?`<p><b>Sustento declarado:</b> ${esc(item.evidencia)}</p>`:''}${item.loteExcel?`<p><b>Archivo:</b> ${esc(item.loteExcel.nombre)} · fila ${esc(item.loteExcel.fila)}</p>`:''}${observations.length?`<p><b>Observaciones:</b></p><ul>${observations.map(entry=>`<li>${esc(entry)}</li>`).join('')}</ul>`:''}${actions?`<div class="matrix-table-actions"><button class="btn" data-viewcase="${esc(item.id)}" aria-label="Ver análisis completo">Análisis</button><button class="btn" data-editcase="${esc(item.id)}" aria-label="Editar este gasto">Editar</button><button class="btn" data-exportcase="${esc(item.id)}" aria-label="Exportar este gasto a Excel">Excel</button><button class="btn danger" data-delcase="${esc(item.id)}" aria-label="Eliminar gasto">Eliminar</button></div>`:''}</div></details>`;
    return `<tr class="matrix-data-row">
      <td class="matrix-date" title="${esc(fullDate)}">${esc(shortDate)}</td>
      <td class="matrix-voucher"><b>${esc(item.numero||'—')}</b><small>${esc(item.tipoComprobante||'')}</small></td>
      <td class="matrix-provider"><b>${esc(item.proveedor||'—')}</b><small>${esc(item.proveedorRuc||'')}</small></td>
      <td class="matrix-concept"><b>${esc(item.descripcionDetalladaGasto||item.concepto||'—')}</b><small>Actividad: ${esc(item.empresaActividad||'No disponible')}</small></td>
      <td class="matrix-number">${money(item.monto||0)}</td>
      <td class="matrix-classification">${evaluationBadge(item)}${identityNeedsReview?'<small class="matrix-identity-warning">RUC por verificar</small>':''}<small class="matrix-inferred-category">Tipo: ${esc(evaluation.expenseCategory||'Gasto empresarial')}</small><small class="matrix-accepted-amount">Deducible: ${value(evaluation.deductibleAmount)}</small><small class="matrix-nondeductible-amount">No deducible/exceso: ${value(evaluation.nonDeductibleAmount)}</small></td>
      <td class="matrix-review">${details}</td>
    </tr>`;
  }).join('');
  return `<div class="table-wrap matrix-table-wrap company-expense-matrix-wrap"><table class="matrix-table company-expense-matrix"><thead><tr><th>Fecha</th><th>Comprobante</th><th>Proveedor / RUC</th><th>Denominación del gasto</th><th>Importe</th><th>Clasificación e importes</th><th>Detalle</th></tr></thead><tbody>${rows||'<tr><td class="matrix-empty" colspan="7">No hay gastos para mostrar.</td></tr>'}</tbody></table></div>`;
}
const MATRIX_PAGE_SIZE=5;
const MATRIX_STATUS_META=[
  {key:'deducible',label:'Deducibles',color:'#2d6d3d',icon:'✓'},
  {key:'no_deducible',label:'No deducibles',color:'#a52d4a',icon:'×'},
  {key:'limitado',label:'Limitados',color:'#d58b23',icon:'⚖'},
  {key:'condicionado',label:'Condicionados',color:'#8750a0',icon:'▤'}
];
function matrixMoney(value){
  return `S/ ${(Number(value)||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}`;
}
function matrixTotals(items){
  const byStatus=Object.fromEntries(MATRIX_STATUS_META.map(meta=>[meta.key,{count:0,gross:0,accepted:0,nonDeductible:0}]));
  let totalAmount=0,deductibleAmount=0,nonDeductibleAmount=0,limitedAccepted=0,conditionedAmount=0;
  items.forEach(item=>{
    const evaluation=caseEvaluation(item),status=byStatus[evaluation.status]?evaluation.status:'condicionado';
    const gross=Math.max(0,Number(item.monto||evaluation.amount||0));
    const accepted=Number(evaluation.deductibleAmount)||0;
    const rejected=Number(evaluation.nonDeductibleAmount)||0;
    const bucket=byStatus[status];
    bucket.count+=1;bucket.gross+=gross;bucket.accepted+=accepted;bucket.nonDeductible+=rejected;
    totalAmount+=gross;
    if(status==='deducible')deductibleAmount+=accepted||gross;
    if(status==='no_deducible')nonDeductibleAmount+=rejected||gross;
    if(status==='limitado')limitedAccepted+=accepted;
    if(status==='condicionado')conditionedAmount+=gross;
  });
  return {byStatus,totalAmount,deductibleAmount,nonDeductibleAmount,limitedAccepted,conditionedAmount};
}
function matrixTable(items,offset=0,actions=true){
  const rows=items.map((item,index)=>{
    const evaluation=caseEvaluation(item);
    const primaryCriterion=(evaluation.criteria||[]).find(criterion=>
      ['Regla específica del concepto','Límite de gastos de representación','Concepto comprendido en una exclusión'].includes(criterion.label)
    )||(evaluation.criteria||[]).find(criterion=>criterion.label==='Vínculo con la actividad empresarial');
    const foundation=primaryCriterion?.reference||(evaluation.legalBasis||[])[0]||'Fundamento pendiente';
    const foundationLabel=foundation.replace(/^LIR,\s*/i,'');
    const foundationType=primaryCriterion?.label||(evaluation.criteria||[]).find(criterion=>criterion.reference===foundation)?.label||'Fundamento normativo';
    return `<tr>
      <td class="matrix-number">${offset+index+1}</td>
      <td class="matrix-company"><b>${esc(item.empresa||'—')}</b><small>RUC ${esc(item.empresaRuc||item.ruc||'—')}</small></td>
      <td class="matrix-date">${esc(item.fecha||'—')}</td>
      <td class="matrix-provider"><b>${esc(item.proveedor||'—')}</b><small>${esc(item.proveedorRuc||'RUC no registrado')}</small></td>
      <td class="matrix-voucher"><b>${esc(item.numero||'—')}</b><small>${esc(item.tipoComprobante||item.tipoOperacion||'Comprobante')}</small></td>
      <td class="matrix-concept" title="${esc(item.descripcionDetalladaGasto||item.concepto||'Descripción pendiente de complementar')}"><b>${esc(item.descripcionDetalladaGasto||item.concepto||'Descripción pendiente de complementar')}</b><small>Actividad: ${esc(item.empresaActividad||'No disponible')}</small></td>
      <td class="matrix-amount">${matrixMoney(item.monto||0)}</td>
      <td class="matrix-classification">${evaluationBadge(item)}</td>
      <td class="matrix-foundation"><b>${esc(foundationLabel)}</b><small>${esc(foundationType)}</small></td>
      ${actions?`<td class="matrix-actions"><button class="matrix-view-button" data-viewcase="${esc(item.id)}" aria-label="Ver análisis de ${esc(item.concepto||'gasto')}" title="Ver análisis"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.8"/></svg></button></td>`:''}
    </tr>`;
  }).join('');
  const columnCount=actions?10:9;
  return `<div class="matrix-table-wrap"><table class="matrix-table"><thead><tr><th>N.º</th><th>Empresa</th><th>Fecha</th><th>Proveedor</th><th>Comprobante</th><th>Descripción detallada / actividad relacionada</th><th>Importe</th><th>Clasificación</th><th>Fundamento (LIR)</th>${actions?'<th aria-label="Acciones"></th>':''}</tr></thead><tbody>${rows||`<tr><td colspan="${columnCount}" class="matrix-table-empty">No hay gastos para mostrar con los filtros seleccionados.</td></tr>`}</tbody></table></div>`;
}
function matrixStatusCards(items){
  const totals=matrixTotals(items);
  return MATRIX_STATUS_META.map(meta=>{
    const bucket=totals.byStatus[meta.key];
    const value=meta.key==='deducible'?totals.deductibleAmount:
      meta.key==='no_deducible'?totals.nonDeductibleAmount:
      meta.key==='limitado'?totals.limitedAccepted:totals.conditionedAmount;
    const caption=meta.key==='limitado'?'Importe aceptado':meta.key==='condicionado'?'Importe pendiente':'Importe clasificado';
    return `<article class="matrix-status-card ${meta.key}"><span class="matrix-status-icon" aria-hidden="true">${meta.icon}</span><div class="matrix-status-copy"><b>${meta.label}</b><strong>${bucket.count}</strong><small>${caption}: ${matrixMoney(value)}</small></div></article>`;
  }).join('');
}
function matrixDashboard(items){
  const totals=matrixTotals(items),pageCount=Math.max(1,Math.ceil(items.length/MATRIX_PAGE_SIZE));
  state.matrixPage=Math.min(Math.max(0,state.matrixPage),pageCount-1);
  const start=state.matrixPage*MATRIX_PAGE_SIZE,pageItems=items.slice(start,start+MATRIX_PAGE_SIZE);
  let cursor=0;
  const segments=MATRIX_STATUS_META.map(meta=>{
    const amount=totals.byStatus[meta.key].gross,from=cursor;
    cursor+=totals.totalAmount?amount/totals.totalAmount*100:0;
    return `${meta.color} ${from.toFixed(2)}% ${cursor.toFixed(2)}%`;
  });
  const chartBackground=totals.totalAmount?`conic-gradient(${segments.join(',')})`:'conic-gradient(#e9ded8 0 100%)';
  const legend=MATRIX_STATUS_META.map(meta=>{
    const bucket=totals.byStatus[meta.key],percentage=totals.totalAmount?bucket.gross/totals.totalAmount*100:0;
    return `<li><span class="matrix-legend-swatch" style="--legend-color:${meta.color}"></span><span>${meta.label} (${percentage.toFixed(1)}%)</span><b>${matrixMoney(bucket.gross)}</b></li>`;
  }).join('');
  const summaryRows=[
    ['Total de gastos evaluados',String(items.length)],
    ['Importe total',matrixMoney(totals.totalAmount)],
    ['Importe deducible',matrixMoney(totals.deductibleAmount)],
    ['Importe no deducible',matrixMoney(totals.nonDeductibleAmount)],
    ['Importe limitado (aceptable)',matrixMoney(totals.limitedAccepted)],
    ['Importe condicionado',matrixMoney(totals.conditionedAmount)]
  ].map(([label,value])=>`<div class="matrix-summary-row"><span>${label}</span><b>${value}</b></div>`).join('');
  const pageButtons=Array.from({length:pageCount},(_,index)=>`<button class="matrix-page-number ${index===state.matrixPage?'active':''}" data-matrix-page="${index}" aria-label="Página ${index+1}" ${index===state.matrixPage?'aria-current="page"':''}>${index+1}</button>`).join('');
  return `<div class="matrix-screen-only">
      <section class="matrix-analysis-panel">
        <div class="matrix-chart-area"><div class="matrix-donut" role="img" aria-label="Distribución de gastos por clasificación" style="--matrix-chart:${chartBackground}"><span><small>Total</small><b>${matrixMoney(totals.totalAmount)}</b></span></div><ul class="matrix-legend">${legend}</ul></div>
        <div class="matrix-summary"><h2><span aria-hidden="true">▥</span> Resumen del análisis</h2>${summaryRows}</div>
      </section>
      <section class="matrix-results-panel"><div class="matrix-results-heading"><h2>Gastos evaluados</h2><span>${items.length} registro(s)</span></div>${matrixTable(pageItems,start)}
        <div class="matrix-footer"><div class="matrix-record-count">Total de registros: <b>${items.length}</b></div><nav class="matrix-pagination" aria-label="Paginación de la matriz"><button class="matrix-page-arrow" data-matrix-page="${Math.max(0,state.matrixPage-1)}" aria-label="Página anterior" ${state.matrixPage===0?'disabled':''}>‹</button>${pageButtons}<button class="matrix-page-arrow" data-matrix-page="${Math.min(pageCount-1,state.matrixPage+1)}" aria-label="Página siguiente" ${state.matrixPage===pageCount-1?'disabled':''}>›</button></nav>
          <div class="matrix-export-actions"><button class="btn matrix-export-excel" id="exportCases"><span aria-hidden="true">▦</span> Exportar a Excel</button></div>
        </div>
      </section>
    </div>
    `;
}
function exportMatrix(items,filename){
  if(!window.XLSX){toast('No se pudo cargar el exportador Excel. Verifica tu conexión e inténtalo nuevamente.');return}
  const rows=[MATRIX_HEADERS,...items.map(matrixValues)];
  const sheet=XLSX.utils.aoa_to_sheet(rows),book=XLSX.utils.book_new();
  sheet['!cols']=MATRIX_HEADERS.map((header,index)=>({wch:[3,4,14,15,16].includes(index)?48:Math.min(Math.max(header.length+2,16),32)}));
  XLSX.utils.book_append_sheet(book,sheet,'Matriz de gastos');
  XLSX.writeFile(book,filename);
}
function exportExpense(expenseId){
  const item=state.cases.find(caseItem=>caseItem.id===expenseId);
  if(item)exportMatrix([item],`gasto_${String(expenseId).replace(/[^a-zA-Z0-9_-]/g,'_')}.xlsx`);
}
function importedBatches(){
  const batches=new Map();
  state.cases.filter(item=>item.origen==='Importación Excel').forEach(item=>{
    const metadata=item.loteExcel||{};
    const id=metadata.id||'importacion-anterior';
    if(!batches.has(id))batches.set(id,{id,name:metadata.nombre||'Importación anterior (lote sin nombre)',date:metadata.fecha||'',items:[]});
    batches.get(id).items.push(item);
  });
  return [...batches.values()].sort((first,second)=>String(second.date).localeCompare(String(first.date)));
}
function caseBatchId(item){
  return item.origen==='Importación Excel'?(item.loteExcel?.id||'importacion-anterior'):null;
}
function exportBatch(batchId){
  const batch=importedBatches().find(item=>item.id===batchId);
  if(!batch)return;
  const filename=`lote_excel_${String(batchId).replace(/[^a-zA-Z0-9_-]/g,'_')}.xlsx`;
  exportMatrix(batch.items,filename);
}
function openCase(id){state.editingCaseId=null;state.selectedCaseId=id;state.selectedCompanyRuc=null;state.page='casos';$$('.nav-item').forEach(button=>button.classList.toggle('active',button.dataset.page==='casos'));render();window.scrollTo(0,0)}
function editCase(id){
  if(!state.cases.some(item=>item.id===id)){toast('No se encontró el gasto que quieres editar.');return}
  state.editingCaseId=id;state.selectedCaseId=null;state.selectedCompanyRuc=null;state.page='nuevo';state.pendingExpenseFiles=[];
  $$('.nav-item').forEach(button=>button.classList.toggle('active',button.dataset.page==='nuevo'));
  render();window.scrollTo(0,0);
}
function openCompany(key){state.editingCaseId=null;state.selectedCaseId=null;state.selectedCompanyRuc=key;state.page='empresas';$$('.nav-item').forEach(button=>button.classList.toggle('active',button.dataset.page==='empresas'));render();window.scrollTo(0,0)}
function wireCaseActions(root=document){
  root.querySelectorAll('[data-editcase]').forEach(button=>button.onclick=()=>editCase(button.dataset.editcase));
  root.querySelectorAll('[data-viewcase]').forEach(button=>button.onclick=()=>openCase(button.dataset.viewcase));
  root.querySelectorAll('[data-exportcase]').forEach(button=>button.onclick=()=>exportExpense(button.dataset.exportcase));
  root.querySelectorAll('[data-delcase]').forEach(button=>button.onclick=async()=>{
    if(!confirm('¿Eliminar este gasto?'))return;
    try{
      await apiRequest(`/api/expenses/${encodeURIComponent(button.dataset.delcase)}`,{method:'DELETE'});
      state.cases=state.cases.filter(item=>item.id!==button.dataset.delcase);
      state.selectedCaseId=null;
    }catch(error){toast(`No se pudo eliminar el gasto: ${error.message}`);return}
    render();
  });
  root.querySelectorAll('[data-delbatch]').forEach(button=>button.onclick=async()=>{
    const batchId=button.dataset.delbatch,batchName=button.dataset.batchName||'este lote';
    const count=state.cases.filter(item=>caseBatchId(item)===batchId).length;
    if(!confirm(`¿Eliminar ${count} gasto(s) y el Excel original de "${batchName}"? Esta acción no se puede deshacer.`))return;
    button.disabled=true;
    try{
      const result=await apiRequest(`/api/expense-batches/${encodeURIComponent(batchId)}`,{method:'DELETE'});
      state.cases=state.cases.filter(item=>caseBatchId(item)!==batchId);
      if(state.selectedCaseId&&!state.cases.some(item=>item.id===state.selectedCaseId))state.selectedCaseId=null;
      render();
      toast(`Se eliminaron ${result.deleted} gasto(s) del lote.`);
    }catch(error){button.disabled=false;toast(`No se pudo eliminar el lote: ${error.message}`)}
  });
  root.querySelectorAll('[data-delallcases]').forEach(button=>button.onclick=async()=>{
    const count=state.cases.length;
    if(!count||!confirm(`¿Eliminar permanentemente los ${count} gastos y todo el historial de esta cuenta? Se conservarán las empresas y los comprobantes independientes.`))return;
    button.disabled=true;
    try{
      const result=await apiRequest('/api/expenses',{method:'DELETE'});
      state.cases=[];
      state.selectedCaseId=null;
      render();
      toast(`Se eliminaron ${result.deleted} gasto(s) del historial.`);
    }catch(error){button.disabled=false;toast(`No se pudo eliminar el historial: ${error.message}`)}
  });
  root.querySelectorAll('[data-company-key]').forEach(button=>button.onclick=()=>openCompany(button.dataset.companyKey));
}
function caseDetail(caseItem){
  const evaluation=caseEvaluation(caseItem),files=Array.isArray(caseItem.archivos)?caseItem.archivos:[];
  const companyRuc=caseItem.empresaRuc||caseItem.ruc||'';
  const criteria=evaluation.criteria||[];
  const display=(value)=>hasCaseValue(value)?esc(value):'No registrado';
  const amount=value=>value===null||value===undefined?'Por determinar':money(value);
  const documents=files.map(file=>{
    if(typeof file==='string')return `<li>${esc(file)}</li>`;
    const link=file.url?`<a href="${esc(file.url)}" target="_blank" rel="noopener noreferrer">${esc(file.name||'Abrir documento')}</a>`:esc(file.name||'Archivo adjunto');
    return `<li>${link}${file.size?` <small>(${(file.size/1024).toFixed(1)} KB)</small>`:''}</li>`;
  }).join('');
  return `${hero('Ficha del gasto',`${caseItem.concepto||'Gasto'} · ${caseItem.id||'Registro histórico'}`)}
    <div class="btn-row detail-actions"><button class="btn" id="backToCases">← Volver al historial</button><button class="btn primary" data-editcase="${esc(caseItem.id)}">Editar caso</button><button class="btn" data-company-key="${esc(companyRuc||`sin-ruc:${caseItem.empresa||''}`)}">Ver gastos de esta empresa</button></div>
    <section class="case-result-panel">${evaluationBadge(caseItem)}<h2>${esc(evaluation.summary)}</h2><div class="stats"><div class="stat"><small>Importe deducible</small><strong>${amount(evaluation.deductibleAmount)}</strong></div><div class="stat"><small>Importe no deducible / exceso</small><strong>${amount(evaluation.nonDeductibleAmount)}</strong></div></div>${evaluation.missing?.length?`<p class="analysis-followup">${evaluation.missing.length} requisito(s) esencial(es) pendiente(s); revisa el detalle normativo.</p>`:''}</section>
    <div class="grid two-col case-detail-grid">
      <section class="panel"><h2>Empresa</h2><dl class="case-facts"><div><dt>Razón social</dt><dd>${display(caseItem.empresa)}</dd></div><div><dt>RUC</dt><dd>${display(companyRuc)}</dd></div><div><dt>Actividad económica principal</dt><dd>${display(caseItem.empresaActividad)}</dd></div><div><dt>Actividad secundaria 1</dt><dd>${display(caseItem.empresaActividadSecundaria1)}</dd></div><div><dt>Actividad secundaria 2</dt><dd>${display(caseItem.empresaActividadSecundaria2)}</dd></div><div><dt>Código CIIU</dt><dd>${display(caseItem.empresaCodigoCIIU)}</dd></div><div><dt>Consulta RUC, fuente y fecha</dt><dd>${display(caseItem.empresaRucStatus||'Pendiente; el proveedor disponible no es SUNAT oficial')} ${caseItem.empresaRucFechaConsulta?`· ${esc(caseItem.empresaRucFechaConsulta)}`:''}</dd></div></dl></section>
      <section class="panel"><h2>Operación</h2><dl class="case-facts"><div><dt>Tipo</dt><dd>${display(caseItem.tipoOperacion)}</dd></div><div><dt>Fecha de operación / servicio</dt><dd>${display(caseItem.fechaServicio||caseItem.fecha)}</dd></div><div><dt>Fecha de comprobante</dt><dd>${display(caseItem.fecha)}</dd></div><div><dt>Descripción detallada del gasto</dt><dd>${display(caseItem.descripcionDetalladaGasto||caseItem.concepto)}</dd></div><div><dt>Finalidad y detalle</dt><dd>${display(caseItem.descripcion)}</dd></div><div><dt>Sustento adicional declarado</dt><dd>${display(caseItem.evidencia)}</dd></div><div><dt>Base imponible / IGV / total</dt><dd>${money(caseItem.baseImponible||0)} / ${money(caseItem.igv||0)} / ${money(caseItem.monto||0)}</dd></div><div><dt>Moneda</dt><dd>${display(caseItem.moneda||'PEN')}</dd></div><div><dt>Medio de pago</dt><dd>${display(caseItem.medioPago)} · ${display(caseItem.referenciaPago)}</dd></div>${caseItem.sireFields?.length?`<div><dt>Periodo SIRE / CAR SUNAT</dt><dd>${display(caseItem.sirePeriod)} / ${display(caseItem.sireCAR||'No informado')}</dd></div>`:''}</dl></section>
      <section class="panel"><h2>Proveedor y comprobante</h2><dl class="case-facts"><div><dt>Proveedor</dt><dd>${display(caseItem.proveedor)}</dd></div><div><dt>RUC proveedor</dt><dd>${display(caseItem.proveedorRuc)}</dd></div><div><dt>Tipo de comprobante</dt><dd>${display(caseItem.tipoComprobante)}</dd></div><div><dt>Serie y número</dt><dd>${display(caseItem.numero)}</dd></div><div><dt>RUC receptor extraído/declarado</dt><dd>${display(caseItem.rucReceptor)}</dd></div><div><dt>Validación del comprobante</dt><dd>${display(caseItem.validacionComprobante||'Pendiente de consulta oficial SUNAT')}</dd></div></dl></section>
      <section class="panel"><h2>Comprobantes y sustentos</h2>${documents?`<ul class="case-file-list">${documents}</ul>`:'<p>No se adjuntaron archivos.</p>'}<p class="footer-note">Los datos extraídos son sugerencias; no equivalen a validar el comprobante ni a acreditar por sí solos la operación.</p></section>
    </div>
    <section class="panel case-criteria-panel"><details class="criteria-disclosure"><summary>Normativa aplicada y criterios de esta evaluación (${criteria.length})</summary>${criteria.length?`<div class="evaluation-criteria">${criteria.map(item=>`<article><div><b>${esc(item.label)}</b><span class="criterion-status ${esc(item.status)}">${item.status==='cumple'?'Indicio favorable':item.status==='no_cumple'?'No cumple':item.status==='no_aplica'?'No aplica':'Pendiente'}</span><p>${esc(item.detail)}</p><a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.reference)} ↗</a></div></article>`).join('')}</div>`:'<p>Este registro histórico no incluye criterios automáticos guardados.</p>'}${[...(evaluation.missing||[]),...(evaluation.observations||[]),...(caseItem.importObservations||[])].length?`<ul class="criteria-observations">${[...(evaluation.missing||[]),...(evaluation.observations||[]),...(caseItem.importObservations||[])].map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:''}</details><p class="footer-note">Evaluación preliminar. La consulta de RUC y la validez del comprobante ante SUNAT son verificaciones independientes y no determinan por sí solas la deducibilidad.</p></section>`;
}
function hasCaseValue(value){return value!==undefined&&value!==null&&String(value).trim()!==''}
function matrices(){
  const selected=state.selectedCaseId?state.cases.find(item=>item.id===state.selectedCaseId):null;
  if(selected)return caseDetail(selected);
  const years=[...new Set(state.cases.map(item=>String(item.fecha||'').slice(0,4)).filter(year=>/^\d{4}$/.test(year)))].sort().reverse();
  return `<section class="matrix-page-header matrix-screen-only"><div class="matrix-page-title"><span class="matrix-page-mark" aria-hidden="true">▥</span><div><span class="guide-kicker">TRIBUANÁLISIS · RENTAS EMPRESARIALES</span><h1>Matriz de clasificación de gastos</h1><p>Evaluación automática y fundamentada de los gastos empresariales.</p></div></div><button class="btn primary" id="newCase">＋ Analizar un gasto</button></section>
    <div id="matrixStatusCards" class="matrix-status-grid matrix-screen-only">${matrixStatusCards(state.cases)}</div>
    <section class="matrix-filter-bar matrix-screen-only"><label class="field"><span aria-hidden="true">▦</span> Empresa<select id="matrixCompanyFilter"><option value="">Todas las empresas</option>${companyGroups().map(group=>`<option value="${esc(group.ruc)}">${esc(group.name)} · ${esc(group.ruc)}</option>`).join('')}</select></label>
      <label class="field"><span aria-hidden="true">▦</span> Periodo<select id="casePeriodFilter"><option value="">Todos los ejercicios</option>${years.map(year=>`<option value="${year}">${year}</option>`).join('')}</select></label>
      <label class="field"><span aria-hidden="true">◇</span> Clasificación<select id="caseFilter"><option value="">Todas</option><option value="deducible">Deducible</option><option value="no_deducible">No deducible</option><option value="limitado">Limitado</option><option value="condicionado">Condicionado</option></select></label>
      <label class="field matrix-search-field"><span aria-hidden="true">⌕</span> Buscar<input id="caseSearch" placeholder="Empresa, proveedor o concepto"></label><button class="btn matrix-filter-button" id="matrixApplyFilters">Filtrar</button>
    </section>
    <div id="matrixContent">${matrixDashboard(state.cases)}</div>`;
}
function casos(){
  const selected=state.selectedCaseId?state.cases.find(item=>item.id===state.selectedCaseId):null;
  if(selected)return caseDetail(selected);
  const years=[...new Set(state.cases.map(item=>String(item.fecha||'').slice(0,4)).filter(year=>/^\d{4}$/.test(year)))].sort().reverse();
  const rows=state.cases.map(item=>{
    const concept=item.descripcionDetalladaGasto||item.denominacion||item.concepto||'—';
    return `<tr class="history-row" data-query="${esc([item.empresa,item.empresaRuc,item.id,item.concepto,item.descripcionDetalladaGasto,item.proveedor].join(' ').toLowerCase())}" data-year="${esc(String(item.fecha||'').slice(0,4))}"><td>${esc(item.fecha||'—')}</td><td>${esc(item.empresa||'—')}<small class="table-subtext">${esc(item.empresaRuc||item.ruc||'')}</small></td><td class="history-concept" title="${esc(concept)}"><span class="history-concept-text">${esc(concept)}</span></td><td>${money(item.monto||0)}</td><td>${evaluationBadge(item)}</td><td class="history-actions"><button class="btn" data-viewcase="${esc(item.id)}" aria-label="Ver análisis">Ver</button><button class="btn" data-editcase="${esc(item.id)}" aria-label="Editar caso">Editar</button><button class="btn" data-exportcase="${esc(item.id)}" aria-label="Exportar caso a Excel">Excel</button><button class="btn danger" data-delcase="${esc(item.id)}" aria-label="Eliminar caso">Eliminar</button></td></tr>`;
  }).join('');
  const batches=importedBatches();
  const batchCards=batches.map(batch=>`<article class="batch-card"><div><b>${esc(batch.name)}</b><small>${batch.items.length} operaciones${batch.date?` · ${esc(batch.date.slice(0,10))}`:''}</small></div><div class="batch-actions"><button class="btn" data-exportbatch="${esc(batch.id)}">Exportar lote a Excel</button><button class="btn danger" data-delbatch="${esc(batch.id)}" data-batch-name="${esc(batch.name)}">Eliminar lote</button></div></article>`).join('');
  return `${hero('Historial de análisis','Revisa las evaluaciones guardadas y abre el detalle documental de cada operación.')}
    ${batches.length?`<section class="panel history-batches"><div class="section-head"><h2>Lotes de Excel importados</h2><span class="pill">${batches.length} lote(s)</span></div><div class="batch-list">${batchCards}</div></section>`:''}
    <div class="section-head history-heading"><h2>Historial de gastos</h2><button class="btn danger" data-delallcases ${state.cases.length?'':'disabled'}>Eliminar todo el historial</button></div>
    <div class="panel"><div class="field-grid"><label class="field">Buscar gasto, empresa o RUC<input id="historySearch" placeholder="Nombre, RUC o código"></label>
    <label class="field">Ejercicio<select id="historyPeriodFilter"><option value="">Todos los ejercicios</option>${years.map(year=>`<option value="${year}">${year}</option>`).join('')}</select></label></div>
    <div class="table-wrap history-table-wrap" style="margin-top:12px"><table class="history-table"><thead><tr><th>Fecha</th><th>Empresa / RUC</th><th>Denominación del gasto</th><th>Importe</th><th>Clasificación automática</th><th>Acciones</th></tr></thead><tbody id="historyList">${rows||'<tr id="historyEmpty"><td colspan="6">Aún no hay análisis.</td></tr>'}<tr id="historyNoResults" hidden><td colspan="6">No hay análisis para estos filtros.</td></tr></tbody></table></div></div>`;
}
function filterHistory(){
  const query=$('#historySearch')?.value.trim().toLowerCase()||'';
  const year=$('#historyPeriodFilter')?.value||'';
  const rows=$$('.history-row');
  let visible=0;
  rows.forEach(row=>{
    const show=(!query||row.dataset.query.includes(query))&&(!year||row.dataset.year===year);
    row.hidden=!show;
    if(show)visible++;
  });
  const empty=$('#historyNoResults');
  const noHistory=$('#historyEmpty');
  if(noHistory)noHistory.hidden=rows.length>0;
  if(empty)empty.hidden=rows.length===0||visible>0;
}
function companyGroups(){
  const groups=new Map();
  state.companies.forEach(company=>{
    const ruc=String(company.ruc||'').trim();
    if(!ruc)return;
    groups.set(ruc,{key:ruc,ruc,name:company.name||company.razonSocial||'Empresa sin nombre',
      activity:company.activity||company.actividadEconomica||'',
      activity1:company.actividadEconomicaSecundaria1||'',activity2:company.actividadEconomicaSecundaria2||'',
      ciiu:company.codigoCIIU||'',source:company.rucLookupSource||'',consultedAt:company.rucLookupDate||'',
      status:company.sunatStatus||'',
      cases:[],documents:[]});
  });
  state.cases.forEach(item=>{
    const ruc=String(item.empresaRuc||item.ruc||'').trim();
    const name=String(item.empresa||'Empresa sin nombre').trim();
    const key=ruc||`sin-ruc:${name}`;
    if(!groups.has(key))groups.set(key,{key,ruc,name,activity:item.empresaActividad||'',
      activity1:item.empresaActividadSecundaria1||'',activity2:item.empresaActividadSecundaria2||'',
      ciiu:item.empresaCodigoCIIU||'',source:item.empresaRucFuente||'',consultedAt:item.empresaRucFechaConsulta||'',
      status:item.empresaRucStatus||'',cases:[],documents:[]});
    const group=groups.get(key);
    if((!group.name||group.name==='Empresa sin nombre')&&name!=='Empresa sin nombre')group.name=name;
    if(!group.activity&&item.empresaActividad)group.activity=item.empresaActividad;
    if(!group.activity1&&item.empresaActividadSecundaria1)group.activity1=item.empresaActividadSecundaria1;
    if(!group.activity2&&item.empresaActividadSecundaria2)group.activity2=item.empresaActividadSecundaria2;
    if(!group.ciiu&&item.empresaCodigoCIIU)group.ciiu=item.empresaCodigoCIIU;
    if(!group.source&&item.empresaRucFuente)group.source=item.empresaRucFuente;
    if(!group.consultedAt&&item.empresaRucFechaConsulta)group.consultedAt=item.empresaRucFechaConsulta;
    if(!group.status&&item.empresaRucStatus)group.status=item.empresaRucStatus;
    group.cases.push(item);
  });
  state.receipts.forEach(document=>{
    const ruc=String(document.empresaRuc||'').trim();
    if(!ruc)return;
    const data=document.datosExtraidos||{};
    if(!groups.has(ruc))groups.set(ruc,{key:ruc,ruc,name:data.empresa||'Empresa sin nombre',activity:'',
      activity1:'',activity2:'',ciiu:'',source:'',consultedAt:'',status:'',cases:[],documents:[]});
    groups.get(ruc).documents.push(document);
  });
  return [...groups.values()].sort((a,b)=>a.name.localeCompare(b.name,'es'));
}
function empresas(){
  const groups=companyGroups();
  const selected=state.selectedCompanyRuc?groups.find(group=>group.key===state.selectedCompanyRuc):null;
  if(selected){
    const years=[...new Set(selected.cases.map(item=>String(item.fecha||'').slice(0,4)).filter(year=>/^\d{4}$/.test(year)))].sort().reverse();
    const docs=selected.documents.map(item=>`<li><a href="${esc(item.url||'#')}" target="_blank" rel="noopener noreferrer">${esc(item.name||'Abrir comprobante')}</a><span>${esc(item.status||'Pendiente de validación')}</span></li>`).join('');
    const statuses=[['deducible','Deducibles'],['no_deducible','No deducibles'],['limitado','Limitados'],['condicionado','Condicionados']];
    const total=selected.cases.reduce((sum,item)=>sum+Number(item.monto||0),0);
    return `<section class="company-page-heading"><div><span class="guide-kicker">EMPRESA Y MATRIZ</span><h1>${esc(selected.name)}</h1><p>RUC ${esc(selected.ruc||'No registrado')}</p></div><div class="btn-row"><button class="btn" id="backToCompanies">← Empresas</button><button class="btn primary" data-go="nuevo">＋ Analizar gasto</button></div></section>
      <section class="company-summary company-summary-compact"><div class="company-summary-info"><span class="company-status-chip">${esc(selected.status||'Estado y condición no registrados')}</span><div class="company-activity-details"><span><b>Actividad principal</b>${esc(selected.activity||'No registrada')}</span><span><b>Actividad secundaria 1</b>${esc(selected.activity1||'No disponible')}</span><span><b>Actividad secundaria 2</b>${esc(selected.activity2||'No disponible')}</span><span><b>Código CIIU</b>${esc(selected.ciiu||'No disponible')}</span></div></div><div class="company-summary-stats"><span><small>Gastos</small><b>${selected.cases.length}</b></span><span><small>Comprobantes</small><b>${selected.documents.length}</b></span><span><small>Importe total</small><b>${money(total)}</b></span></div></section>
      <section class="company-status-grid">${statuses.map(([status,label])=>`<div class="company-status-card status-${status}"><small>${label}</small><b>${selected.cases.filter(item=>caseEvaluation(item).status===status).length}</b></div>`).join('')}</section>
      <section class="panel company-matrix-panel"><div class="section-head"><div><span class="guide-kicker">REGISTRO ACUMULATIVO</span><h2>Matriz de evaluación</h2></div><button class="btn primary" id="exportCompanyMatrix">Exportar a Excel</button></div><div class="company-filter-bar"><label class="field">Ejercicio<select id="companyPeriodFilter"><option value="">Todos los años</option>${years.map(year=>`<option value="${year}">${year}</option>`).join('')}</select></label><label class="field">Clasificación<select id="companyClassFilter"><option value="">Todas</option><option value="deducible">Deducible</option><option value="no_deducible">No deducible</option><option value="limitado">Limitado</option><option value="condicionado">Condicionado</option></select></label></div><div id="companyCaseList">${caseTable(selected.cases)}</div></section>
      <section class="panel company-documents-panel"><h2>Comprobantes asociados</h2>${docs?`<ul class="case-file-list">${docs}</ul>`:'<p>No hay comprobantes asociados a esta empresa.</p>'}</section>`;
  }
  return `${hero('Empresas','Cada empresa conserva su propia matriz, gastos y comprobantes.')}
    <section class="panel company-register-panel"><div><span class="guide-kicker">NUEVA EMPRESA</span><h2>Registrar o actualizar empresa</h2><p>Busca el RUC para completar los datos disponibles o ingrésalos manualmente.</p></div><div class="field-grid">
      ${sunatRucField('RUC de la empresa','companyRuc')}${field('Razón social','companyName','')}
      ${field('Actividad económica principal','companyActivity','')}<input type="hidden" id="companyRucStatus">
    </div><div class="btn-row"><button class="btn primary" id="saveCompany">Guardar empresa</button></div></section>
    <section class="company-groups company-groups-compact">${groups.length?groups.map(group=>`<article class="company-group-card"><div class="company-group-heading"><span class="company-group-icon">▤</span><div><h2>${esc(group.name)}</h2><p>RUC ${esc(group.ruc||'No registrado')}</p></div></div><p class="company-card-activity">${esc(group.activity||'Actividad económica pendiente de registro')}</p><div class="company-card-footer"><span><b>${group.cases.length}</b> gastos</span><span><b>${group.documents.length}</b> comprobantes</span><span><b>${money(group.cases.reduce((sum,item)=>sum+Number(item.monto||0),0))}</b> total</span></div><button class="btn primary" data-company-key="${esc(group.key)}">Abrir matriz <span aria-hidden="true">→</span></button></article>`).join(''):'<div class="panel empty-company-state"><h2>Aún no hay empresas registradas</h2><p>Registra una empresa aquí o incorpora sus gastos mediante cualquiera de las modalidades.</p><button class="btn primary" data-go="nuevo">＋ Analizar un gasto</button></div>'}</section>`;
}
function guia(){
 const principles=[
   {symbol:'01',title:'Causalidad',image:'causalidad.svg',alt:'Relación entre el gasto y la actividad empresarial',description:'El artículo 37 permite deducir los gastos necesarios para producir rentas gravadas o mantener la fuente. No basta con que el gasto ocurra dentro de la empresa: debe explicarse qué función cumple en sus operaciones.',reference:'Ley del Impuesto a la Renta · artículo 37, primer párrafo',links:[['Artículo 37, primer párrafo',SUNAT_LAW_URLS.lir37]]},
   {symbol:'02',title:'Fehaciencia',image:'fehaciencia.svg',alt:'Documentos que acreditan una operación',description:'La factura acredita que se emitió un comprobante, pero no demuestra por sí sola que el bien se entregó o que el servicio se prestó. Órdenes, contratos, entregables, comunicaciones y constancias de recepción ayudan a reconstruir la operación.',reference:'Ley del Impuesto a la Renta · artículo 37, primer párrafo',links:[['Artículo 37, primer párrafo',SUNAT_LAW_URLS.lir37]]},
   {symbol:'03',title:'Razonabilidad y proporcionalidad',image:'razonabilidad.svg',alt:'Evaluación de la proporción entre el gasto y las operaciones',description:'El monto se contrasta con la naturaleza y escala del negocio, el volumen de operaciones, la finalidad y las circunstancias concretas. No existe una proporción única que vuelva automáticamente deducible o no deducible todo gasto.',reference:'Ley del Impuesto a la Renta · artículo 37, último párrafo',links:[['Artículo 37, último párrafo',SUNAT_LAW_URLS.lir37Reasonableness]]},
   {symbol:'04',title:'Devengo',image:'devengo.svg',alt:'Calendario del periodo en que se reconoce un gasto',description:'Como regla, el gasto corresponde al ejercicio en que ocurren los hechos sustanciales que generan la obligación, aunque el pago se realice en otro momento. Deben revisarse las reglas especiales aplicables al tipo de operación.',reference:'Ley del Impuesto a la Renta · artículo 57, inciso a)',links:[['Artículo 57, inciso a)',SUNAT_LAW_URLS.lir57]]},
   {symbol:'05',title:'Bancarización',image:'bancarizacion.svg',alt:'Medios de pago y constancia bancaria',description:'Cuando la operación alcanza el umbral legal, debe utilizarse un medio de pago admitido. Conserva la constancia y vincúlala con el comprobante: no basta con que exista una transferencia si no puede identificarse la operación.',reference:'Ley 28194 · artículos 3, 4 y 8',links:[['Artículo 3 · ámbito de aplicación',SUNAT_LAW_URLS.paymentMethods3],['Artículo 4 · medios de pago',SUNAT_LAW_URLS.paymentMethods4],['Artículo 8 · efectos tributarios',SUNAT_LAW_URLS.paymentMethods8]]},
   {symbol:'06',title:'Límites y prohibiciones',image:'limites-prohibiciones.svg',alt:'Reglas que restringen o prohíben la deducción de gastos',description:'Algunos gastos solo se aceptan hasta un límite o si cumplen requisitos especiales. Otros están expresamente excluidos por ley. Revisa cada regla según el concepto y las circunstancias del gasto.',reference:'Ley del Impuesto a la Renta · artículo 37, incisos aplicables, y artículo 44',topics:[
     {title:'Representación · artículo 37, inciso q)',text:'Son deducibles los gastos de representación propios del giro dentro del límite legal y si se acredita su relación con la actividad; separa los gastos personales o ajenos al negocio.',url:SUNAT_LAW_URLS.lir37Representation},
     {title:'Viajes · artículo 37, inciso r)',text:'Los viajes deben responder a necesidades del negocio y contar con documentación. La deducción está sujeta a topes y reglas específicas para transporte y viáticos.',url:SUNAT_LAW_URLS.lir37Travel},
     {title:'Vehículos · artículo 37, inciso w)',text:'La deducción puede estar limitada por la categoría, número de vehículos y uso. Registra la asignación y el uso empresarial; el gasto no se presume deducible solo por estar a nombre de la empresa.',url:SUNAT_LAW_URLS.lir37Vehicles},
     {title:'Donaciones · artículo 37, inciso x)',text:'Solo se aceptan bajo condiciones legales, incluyendo destinatarios habilitados y límites. Verifica la calificación del receptor y el comprobante de entrega.',url:SUNAT_LAW_URLS.lir37Donations},
     {title:'Beneficios al personal · generalidad',text:'Cuando la norma exige generalidad, el beneficio debe otorgarse con criterios objetivos a quienes se encuentren en condiciones comparables; revisa también las reglas específicas del concepto.',url:SUNAT_LAW_URLS.lir37General},
     {title:'Gastos prohibidos · artículo 44',text:'El artículo 44 excluye conceptos como gastos personales, multas e impuesto a la renta, además de otros supuestos. Identifica la prohibición concreta antes de clasificar.',url:SUNAT_LAW_URLS.lir44}
   ]}
 ];
 return `<section class="normative-overview"><div><span class="guide-kicker">GUÍA PRÁCTICA · IMPUESTO A LA RENTA</span><h1>Entiende la regla antes de aplicarla</h1><p>Una explicación breve de cada criterio, qué documentos revisar y el enlace directo al artículo o inciso correspondiente.</p></div><img src="assets/images/normativa-aplicada/dashboard-tributario.jpg" alt="Material de consulta para la evaluación tributaria"></section>
   <div class="principle-grid applied-principle-grid">${principles.map(rule=>`<article class="principle-card applied-principle-card"><img class="principle-illustration" src="assets/images/normativa/${esc(rule.image)}" alt="${esc(rule.alt)}" loading="lazy"><div class="principle-content"><span class="principle-category">CRITERIO ${rule.symbol}</span><h2>${esc(rule.title)}</h2><p>${esc(rule.description)}</p><details class="law-details"><summary><span>Explicación y fundamento legal</span><span aria-hidden="true">⌄</span></summary><div class="law-detail-content"><b>${esc(rule.reference)}</b>${rule.topics?`<div class="law-topic-list">${rule.topics.map(topic=>`<article class="law-topic"><h3>${esc(topic.title)}</h3><p>${esc(topic.text)}</p><a href="${esc(topic.url)}" target="_blank" rel="noopener noreferrer">Abrir artículo o inciso ↗</a></article>`).join('')}</div>`:`<p>Consulta el texto legal citado y revisa cómo se aplica a los hechos y documentos de la operación.</p>${rule.links.map(([label,url])=>`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`).join('')}`}</div></details></div></article>`).join('')}</div>
   <div class="notice applied-law-note">La evaluación es una ayuda para el análisis. La deducción final depende de la documentación, el ejercicio y la normativa vigente que corresponda a cada operación.</div>`;
}
function perfil(){const members=['CHAVARREA TANTA, LIZ ROSMERY','PORTALES PAIRAZAMAN, NOEMI ARACELI','RAMOS NOVOA, MARÍA ROXANA','TERAN CABANILLAS, TREISY JOSSEPH','VASQUEZ TARRILLO, RUT YUDIT','VIDAURRE ROJAS, MELANY LAYLIN'];return `${hero('Usuario y equipo','Consulta los datos de tu cuenta y conoce al equipo de Tribuanálisis.')}<div class="grid two-col"><section class="panel user-profile-card"><div class="profile-avatar">${esc((state.profile.name||'U').trim().charAt(0).toUpperCase())}</div><span class="guide-kicker">CUENTA ACTIVA</span><h2>${esc(state.profile.name||'Usuario')}</h2><p>${esc(state.profile.email||'')}</p><div class="user-course-badge">TRIBUTACIÓN II · UNIDAD II</div><hr><h3>Seguridad</h3><label class="field">Nueva contraseña<input type="password" id="newPassword" minlength="6" autocomplete="new-password" placeholder="Mínimo 6 caracteres"></label><button class="btn primary" id="changePassword">Actualizar contraseña</button><p class="footer-note">La cuenta y los datos de trabajo se guardan de forma persistente en la base de datos.</p></section><section class="panel project-team-card"><span class="guide-kicker">PROYECTO ACADÉMICO</span><h2>Integrantes</h2><ol class="team-list">${members.map((name,index)=>`<li><span>${String(index+1).padStart(2,'0')}</span><strong>${name}</strong></li>`).join('')}</ol><div class="teacher-card"><span>DOCENTE</span><strong>C.P.C. ALTAMIRANO SALINAS, MARLENE LOURDES</strong><small>Curso: Tributación II</small></div></section></div>`}

function nuevo(){
  const editing=state.cases.find(item=>item.id===state.editingCaseId)||null;
  if(state.editingCaseId&&!editing)state.editingCaseId=null;
  state.expenseEvaluation=null;
  const savedDocuments=(editing?.archivos||[]).map(file=>{
    if(typeof file==='string')return `<li>${esc(file)}</li>`;
    const link=file.url?`<a href="${esc(file.url)}" target="_blank" rel="noopener noreferrer">${esc(file.name||'Abrir documento')}</a>`:esc(file.name||'Archivo adjunto');
    return `<li>${link}</li>`;
  }).join('');
  return `${hero(editing?'Editar gasto':'Matriz de evaluación de gastos empresariales',editing?'Actualiza los datos del caso; al guardar se volverá a calcular su evaluación.':'Registra los datos y el sustento de la operación. El motor analiza los criterios y la clasificación automáticamente.')}
  <div class="panel analysis-form-panel"><h2>${editing?'Editar operación existente':'Empresa y operación'}</h2>${editing?'<div class="notice">Se conservarán el identificador, los documentos asociados y el lote de origen de este caso.</div>':''}<div class="field-grid" id="expenseAnalysisForm">
    ${sunatRucField('RUC de la empresa receptora','caseCompanyRuc')}${field('Razón social de la empresa','caseCompanyName','')}${field('Actividad económica de la empresa','caseCompanyActivity','')}
    <input type="hidden" id="caseCompanyStatus"><input type="hidden" id="caseRucStatus">
    ${selectField('Tipo de operación','caseType',['Compra de bienes','Servicio recibido','Gasto de personal','Gasto financiero','Activo fijo','Otro'],'Compra de bienes')}
    ${selectField('Tipo de comprobante','caseVoucherType',['Factura','Boleta de venta','Recibo por honorarios','Ticket','Nota de crédito','Nota de débito','Otro'],'Factura')}
    ${field('Fecha del comprobante / operación','caseDate',new Date().toISOString().slice(0,10),'date')}${field('Fecha de recepción o prestación','caseServiceDate','','date')}
    ${sunatRucField('RUC del proveedor/emisor','caseProviderRuc')}${field('Proveedor / razón social','caseProvider','')}${field('Serie y número del comprobante','caseNumber','')}
    ${field('RUC receptor que figura en el comprobante','caseReceiverRuc','')}${selectField('Moneda','caseCurrency',['PEN','USD','EUR'],'PEN')}
    ${field('Base imponible','caseTaxBase','','number')}${field('IGV','caseIGV','','number')}${field('Importe total','caseAmount','','number')}
    ${field('Presupuesto / valor de referencia (opcional)','caseReferenceAmount','','number')}${field('Ingresos netos del ejercicio (para límites legales)','caseGrossIncome','','number')}
    ${selectField('Medio de pago','casePaymentMethod',['No registrado','Efectivo','Transferencia','Tarjeta','Cheque','Otro'],'No registrado')}${field('Referencia del pago','casePaymentReference','')}
  </div>
  <label class="field">Concepto del gasto<input id="caseConcept" placeholder="Bien o servicio descrito en la operación"></label>
  <label class="field">Finalidad y detalle de la operación<textarea id="caseDesc" placeholder="Describe qué se adquirió, para qué proceso/actividad se usó y, si aplica, el periodo del servicio."></textarea></label>
  <label class="field">Sustento adicional disponible<textarea id="caseEvidence" placeholder="Contratos, órdenes, entregas, informes, cotizaciones u otros documentos que se adjuntan."></textarea></label>
  ${savedDocuments?`<section class="saved-expense-documents"><b>Documentos ya asociados</b><ul class="case-file-list">${savedDocuments}</ul><small>Estos archivos se conservarán al guardar los cambios.</small></section>`:''}
  <label class="field">Comprobante y sustentos<input type="file" id="caseFiles" accept=".xml,.pdf,.jpg,.jpeg,.png" multiple><small>XML, PDF, JPG o PNG · Los campos reconocidos se completan como sugerencia y deben revisarse.</small></label>
  <div id="expenseDocumentPreview"></div><div class="notice manual-receipt-check" role="status">Validación del comprobante ante SUNAT: pendiente; la comparación de RUC no confirma autenticidad ni deducibilidad.</div></div>
  <div class="panel analysis-result-panel" style="margin-top:14px"><h2>Resultado automático</h2><div id="evaluationPreview" aria-live="polite"><div class="notice">La evaluación se actualizará conforme se ingresen datos y se adjunten documentos.</div></div>
  <div class="btn-row"><button type="button" class="btn primary" id="saveManualCase" disabled>${editing?'Guardar cambios y reevaluar':'Guardar evaluación y comprobantes'}</button><button type="button" class="btn" id="clearManualCase">${editing?'Cancelar edición':'Limpiar formulario'}</button></div>
  <p class="footer-note">No respondas cuestionarios ni selecciones una clasificación. El sistema informa Deducible, No deducible, Limitado o Condicionado según los datos disponibles y muestra sus fundamentos.</p></div>`;
}
function comprobantes(){
  return `${hero('Comprobantes empresariales','Carga documentos para extraer sus datos y asociarlos con la empresa identificada por su RUC.')}
    <section class="panel receipt-company-panel"><h2>Empresa propietaria</h2><div class="field-grid">${sunatRucField('RUC de la empresa','receiptReceiverRuc')}${field('Razón social','receiptReceiverName','')}</div></section>
    <section class="panel receipt-upload-panel" style="margin-top:14px"><h2>Subir y extraer comprobantes</h2><div class="dropzone" id="receiptDrop"><div style="font-size:38px;color:var(--wine)">⇧</div><b>Arrastra XML, PDF o imágenes, o selecciónalos</b><p>XML, PDF, JPG o PNG · hasta 10 documentos por carga</p><input type="file" id="receiptFiles" accept=".xml,.pdf,.jpg,.jpeg,.png" multiple></div><div id="receiptPreview"></div></section>
    <section class="panel" style="margin-top:14px"><h2>Historial de comprobantes</h2><div class="table-wrap"><table><thead><tr><th>Archivo</th><th>Empresa / RUC</th><th>Proveedor / RUC</th><th>Fecha</th><th>Validación SUNAT</th><th>Documento</th></tr></thead><tbody id="receiptHistoryRows">${receiptHistoryRows()}</tbody></table></div><p class="footer-note">El contenido se procesa y conserva localmente en SQLite. La validación CPE permanece pendiente hasta recibir una respuesta de un servicio oficial habilitado.</p></section>`;
}
function masiva(){return `${hero('Carga masiva de gastos empresariales','Importa el Registro de Compras SIRE y genera una matriz separada por cada RUC de empresa.')}<div class="grid two-col"><div class="panel"><h2>Plantilla y casos de prueba</h2><p>Se aceptan libros SIRE originales de 80 columnas y el formato personalizado de 81 columnas con descripción detallada. La clasificación siempre la calcula la aplicación.</p><div class="btn-row"><a class="btn primary" href="/api/expense-template.xlsx">⇩ Descargar plantilla vacía</a><a class="btn" href="/api/case-test-template.xlsx">Descargar Excel de casos de prueba</a></div></div><div class="panel"><h2>Lectura y complementación</h2><p>Los encabezados se detectan por nombre; CAR SUNAT puede estar vacío. Si el libro incluye «Contexto de casos», se relaciona por RUC empresa, periodo, comprobante, serie, número y RUC proveedor.</p><div class="notice">La descripción detallada y la finalidad pueden completarse en la vista previa; la evidencia de recepción y otros sustentos se incorporan en «Contexto de casos». La validación oficial de comprobantes permanece separada de la evaluación tributaria.</div></div></div><div class="panel" style="margin-top:14px"><h2>Importar archivo Excel</h2><div class="dropzone" id="bulkDrop"><div style="font-size:38px">▦</div><b>Arrastra tu archivo aquí</b><p>Formato .xlsx o .xls</p><input type="file" id="bulkExcel" accept=".xlsx,.xls"></div><div id="bulkPreview"></div></div>`}

function receiptHistoryRows(){
  return state.receipts.map(receipt=>{
    const data=receipt.datosExtraidos||{};
    const name=receipt.url?`<a href="${esc(receipt.url)}" target="_blank" rel="noopener noreferrer">${esc(receipt.name||'Abrir documento')}</a>`:esc(receipt.name||'—');
    return `<tr><td>${name}</td><td>${esc(receipt.empresaRuc||'—')}</td><td>${esc(data.proveedor||receipt.company||'—')} / ${esc(data.proveedorRuc||receipt.proveedorRuc||'—')}</td><td>${esc(data.fecha||receipt.date||'—')}</td><td><span class="pill">${esc(receipt.status||'Pendiente de consulta oficial SUNAT')}</span></td><td>${esc(data.numero||'—')}</td></tr>`;
  }).join('')||'<tr><td colspan="6">Aún no hay comprobantes cargados.</td></tr>';
}
function hydrateExpenseEditForm(){
  const item=state.cases.find(caseItem=>caseItem.id===state.editingCaseId);
  if(!item||!$('#expenseAnalysisForm'))return;
  const values={
    caseCompanyRuc:item.empresaRuc||item.ruc||'',
    caseCompanyName:item.empresa||'',
    caseCompanyActivity:item.empresaActividad||'',
    caseType:item.tipoOperacion||'Compra de bienes',
    caseVoucherType:item.tipoComprobante||'Factura',
    caseDate:item.fecha||'',
    caseServiceDate:item.fechaServicio||'',
    caseProviderRuc:item.proveedorRuc||'',
    caseProvider:item.proveedor||'',
    caseNumber:item.numero||'',
    caseReceiverRuc:item.rucReceptor||'',
    caseCurrency:item.moneda||'PEN',
    caseTaxBase:item.baseImponible??'',
    caseIGV:item.igv??'',
    caseAmount:item.monto??'',
    caseReferenceAmount:item.importeReferencia??'',
    caseGrossIncome:item.ingresosNetosAnuales??'',
    casePaymentMethod:item.medioPago||'No registrado',
    casePaymentReference:item.referenciaPago||'',
    caseConcept:item.concepto||item.descripcionDetalladaGasto||'',
    caseDesc:item.descripcion||'',
    caseEvidence:item.evidencia||''
  };
  Object.entries(values).forEach(([id,value])=>{
    const element=$(`#${id}`);
    if(!element)return;
    const text=String(value??'');
    if(element instanceof HTMLSelectElement&&text&&!Array.from(element.options).some(option=>option.value===text)){
      const option=document.createElement('option');
      option.value=text;option.textContent=text;element.append(option);
    }
    element.value=text;
  });
  $('#caseCompanyStatus').value=item.empresaRucStatus||'';
  $('#caseRucStatus').value=item.proveedorRucSunatStatus||'';
  const companyDetails=$('[data-ruc-details="caseCompanyRuc"]');
  if(companyDetails)companyDetails.dataset.lookup=JSON.stringify({
    actividadEconomicaSecundaria1:item.empresaActividadSecundaria1||'',
    actividadEconomicaSecundaria2:item.empresaActividadSecundaria2||'',
    codigoCIIU:item.empresaCodigoCIIU||'',
    source:item.empresaRucFuente||'',
    consultedAt:item.empresaRucFechaConsulta||''
  });
}
function render(){let pages={home,empresas,nuevo,comprobantes,masiva,matrices,casos,guia,perfil};$('#view').innerHTML=pages[state.page]();wire()}
function wire(){
$$('[data-go]').forEach(b=>b.onclick=()=>go(b.dataset.go));
wireCaseActions();
hydrateExpenseEditForm();
$$('[data-tab]').forEach(b=>b.onclick=()=>{state.tab=b.dataset.tab;render()});
$$('[data-ruc-search]').forEach(button=>button.onclick=()=>lookupRuc($('#'+button.dataset.rucSearch)));
$$('[data-ruc-input]').forEach(input=>{
  input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();lookupRuc(input)}});
  input.addEventListener('input',()=>clearStaleLookup(input));
});
$('#expenseAnalysisForm')?.addEventListener('input',invalidateExpenseEvaluation);
$('#expenseAnalysisForm')?.addEventListener('change',invalidateExpenseEvaluation);
$('#caseDesc')?.addEventListener('input',invalidateExpenseEvaluation);
$('#caseEvidence')?.addEventListener('input',invalidateExpenseEvaluation);
$('#caseConcept')?.addEventListener('input',invalidateExpenseEvaluation);
$('#caseFiles')?.addEventListener('change',event=>handleExpenseFiles(event.target.files));
if($('#evaluationPreview'))invalidateExpenseEvaluation();
$('#backToCases')?.addEventListener('click',()=>{state.selectedCaseId=null;render();window.scrollTo(0,0)});
$('#backToCompanies')?.addEventListener('click',()=>{state.selectedCompanyRuc=null;render();window.scrollTo(0,0)});
if($('#saveEmpresa'))$('#saveEmpresa').onclick=()=>{let map={razon:'eRazon',ruc:'eRuc',tipo:'eTipo',tamano:'eTam',fecha:'eFecha',domicilio:'eDom'};Object.entries(map).forEach(([k,id])=>{if($('#'+id))state.empresa[k]=$('#'+id).value});if($('#fIng'))state.fin.ingresos=Number($('#fIng').value);if($('#fCos'))state.fin.costos=Number($('#fCos').value);if($('#fGas'))state.fin.gastos=Number($('#fGas').value);saveWorkspace();toast('Información empresarial guardada en tu cuenta.');render()};
if($('#clearForm'))$('#clearForm').onclick=()=>toast('Puedes reemplazar los campos para actualizar la información.');
if($('#newCase'))$('#newCase').onclick=()=>go('nuevo');
if($('#caseSearch'))$('#caseSearch').oninput=filterCases;
if($('#matrixCompanyFilter'))$('#matrixCompanyFilter').onchange=filterCases;
if($('#caseFilter'))$('#caseFilter').onchange=filterCases;
if($('#casePeriodFilter'))$('#casePeriodFilter').onchange=filterCases;
if($('#matrixApplyFilters'))$('#matrixApplyFilters').onclick=filterCases;
if($('#matrixContent'))wireMatrixContent($('#matrixContent'));
if($('#historySearch'))$('#historySearch').oninput=filterHistory;
if($('#historyPeriodFilter'))$('#historyPeriodFilter').onchange=filterHistory;
if($('#companyPeriodFilter'))$('#companyPeriodFilter').onchange=filterCompanyCases;
if($('#companyClassFilter'))$('#companyClassFilter').onchange=filterCompanyCases;
if($('#exportCases'))$('#exportCases').onclick=()=>exportMatrix(filteredCaseItems(),'matriz_gastos_empresariales.xlsx');
if($('#exportCompanyMatrix'))$('#exportCompanyMatrix').onclick=()=>exportMatrix(companyFilteredCaseItems(),'matriz_empresa.xlsx');
$$('[data-exportbatch]').forEach(button=>button.onclick=()=>exportBatch(button.dataset.exportbatch));
if($('#saveProfile'))$('#saveProfile').onclick=()=>{state.profile={name:$('#pName').value,email:$('#pEmail').value,dni:$('#pDni').value,career:$('#pCareer').value,cycle:$('#pCycle').value};saveWorkspace();$('#topShortName').textContent=shortUserName(state.profile.name);$('#topAvatar').textContent=shortUserName(state.profile.name).charAt(0).toUpperCase();$('#menuUserName').textContent=state.profile.name;toast('Perfil actualizado.')};
if($('#saveCompany'))$('#saveCompany').onclick=async()=>{
  const ruc=$('#companyRuc').value.trim(),name=$('#companyName').value.trim(),activity=$('#companyActivity').value.trim();
  if(!isValidRuc(ruc)||!name){toast('Ingresa un RUC válido y la razón social de la empresa.');return}
  const previous=state.companies;
  const lookup=rucLookupData('companyRuc');
  const company={...(previous.find(item=>item.ruc===ruc)||{}),ruc,name,activity,
    actividadEconomicaPrincipal:activity,
    actividadEconomicaSecundaria1:lookup.actividadEconomicaSecundaria1||'',
    actividadEconomicaSecundaria2:lookup.actividadEconomicaSecundaria2||'',
    codigoCIIU:lookup.codigoCIIU||'',
    rucLookupSource:lookup.source||'',rucLookupDate:lookup.consultedAt||'',
    rucLookupOfficial:lookup.official===true,
    sunatStatus:$('#companyRucStatus').value||''};
  state.companies=[...previous.filter(item=>item.ruc!==ruc),company];
  if(!await saveWorkspace()){state.companies=previous;return}
  toast('Empresa guardada en la base de datos de tu cuenta.');
  render();
};
if($('#changePassword'))$('#changePassword').onclick=async()=>{
  const password=$('#newPassword').value;
  if(password.length<6){toast('La nueva contraseña debe tener al menos 6 caracteres.');return}
  try{
    await apiRequest('/api/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
    const list=accounts(),user=list.find(account=>account.email===state.activeEmail);
    if(user){user.passwordHash=await passwordHash(password);localStorage.setItem(ACCOUNT_KEY,JSON.stringify(list))}
    $('#newPassword').value='';
    toast('Contraseña actualizada en la base de datos.');
  }catch(error){toast(error.message)}
};
if($('#saveManualCase'))$('#saveManualCase').onclick=async()=>{
  const current=expenseFormData();
  const hasElevenDigitRuc=value=>/^\d{11}$/.test(String(value||'').trim());
  const validCompanyRuc=state.editingCaseId?hasElevenDigitRuc(current.empresaRuc):isValidRuc(current.empresaRuc);
  const validProviderRuc=state.editingCaseId?hasElevenDigitRuc(current.proveedorRuc):isValidRuc(current.proveedorRuc);
  if(!validCompanyRuc||!current.empresa||!current.proveedor||!validProviderRuc||!current.numero||!current.concepto||!(current.monto>0)||!current.fecha){
    toast('Completa la empresa, fecha, proveedor y RUC, comprobante, concepto e importe mayor que cero.');
    return;
  }
  const button=$('#saveManualCase');
  button.disabled=true;
  try{
    const editingId=state.editingCaseId;
    const existing=editingId?state.cases.find(caseItem=>caseItem.id===editingId):null;
    if(editingId&&!existing)throw new Error('El gasto que intentas editar ya no está en el historial.');
    const result=await evaluateExpense(current);
    const receiverMatch=current.rucReceptor?current.rucReceptor===current.empresaRuc:null;
    const item={...(existing||{}),...current,
      empresaActividadSecundaria1:current.empresaActividadSecundaria1||existing?.empresaActividadSecundaria1||'',
      empresaActividadSecundaria2:current.empresaActividadSecundaria2||existing?.empresaActividadSecundaria2||'',
      empresaCodigoCIIU:current.empresaCodigoCIIU||existing?.empresaCodigoCIIU||'',
      empresaRucFuente:current.empresaRucFuente||existing?.empresaRucFuente||'',
      empresaRucFechaConsulta:current.empresaRucFechaConsulta||existing?.empresaRucFechaConsulta||'',
      documentos:[...(existing?.documentos||[]),...(current.documentos||[])],
      archivos:Array.isArray(existing?.archivos)?[...existing.archivos]:[],
      id:existing?.id||`CAS-${crypto.randomUUID?.()||Date.now()}`,
      ruc:current.empresaRuc,
      estado:result.status,clasificacion:result.label,
      rucReceptorCoincide:receiverMatch,validacionComprobante:'Pendiente de consulta oficial SUNAT',
      evaluation:result,createdAt:existing?.createdAt||new Date().toISOString()};
    const originalCases=state.cases;
    state.cases=existing
      ?state.cases.map(caseItem=>caseItem.id===item.id?item:caseItem)
      :[item,...state.cases];
    if(!await saveCases()){state.cases=originalCases;throw new Error('No se pudo guardar el gasto en la base de datos.')}
    const savedItem=state.cases.find(caseItem=>caseItem.id===item.id)||item;
    for(const pending of state.pendingExpenseFiles){
      try{
        const form=new FormData();
        form.append('document',pending.file,pending.name);
        form.append('companyRuc',current.empresaRuc);
        form.append('expenseId',item.id);
        const document=await apiRequest('/api/documents',{method:'POST',body:form});
        savedItem.archivos.push(document);
      }catch(error){toast(`No se guardó ${pending.name}: ${error.message}`)}
    }
    if(!await saveCases())throw new Error('No se pudieron guardar los comprobantes asociados al gasto.');
    state.selectedCaseId=item.id;
    state.editingCaseId=null;
    state.expenseEvaluation=null;
    state.pendingExpenseFiles=[];
    state.page='casos';
    $$('.nav-item').forEach(nav=>nav.classList.toggle('active',nav.dataset.page==='casos'));
    render();
    window.scrollTo(0,0);
    toast(existing?`Cambios guardados y reevaluados: ${savedItem.evaluation.label}.`:`Evaluación guardada: ${savedItem.evaluation.label}.`);
  }catch(error){
    button.disabled=false;
    toast(`No se pudo guardar la evaluación: ${error.message}`);
  }
};
if($('#clearManualCase'))$('#clearManualCase').onclick=()=>{
  if(state.editingCaseId){
    const caseId=state.editingCaseId;
    state.editingCaseId=null;
    state.pendingExpenseFiles=[];
    openCase(caseId);
    return;
  }
  $$('#view input, #view textarea').forEach(input=>{if(input.type!=='file')input.value=''});
  if($('#caseFiles'))$('#caseFiles').value='';
  if($('#caseDate'))$('#caseDate').value=new Date().toISOString().slice(0,10);
  $$('#view select').forEach(select=>select.selectedIndex=0);
  state.pendingExpenseFiles=[];
  state.expenseEvaluation=null;
  $('#saveManualCase').disabled=true;
  $('#expenseDocumentPreview').innerHTML='';
  $('#evaluationPreview').innerHTML='<div class="notice">La evaluación se actualizará conforme se ingresen datos y se adjunten documentos.</div>';
};
async function handleExpenseFiles(files){
  const list=[...files];
  if(!list.length)return;
  if(list.length>10){toast('Adjunta hasta 10 documentos por carga.');return}
  const form=new FormData();
  list.forEach(file=>form.append('documents',file,file.name));
  const preview=$('#expenseDocumentPreview');
  preview.innerHTML='<div class="notice">Extrayendo datos de los documentos…</div>';
  try{
    const result=await apiRequest('/api/documents/extract',{method:'POST',body:form});
    state.pendingExpenseFiles=result.documents.map((document,index)=>({...document,file:list[index],size:list[index]?.size||0}));
    const extracted=result.documents[0]?.datosExtraidos||{};
    const fill=(id,value)=>{
      const input=$('#'+id);
      if(input&&value&&!input.value){
        input.value=value;
        input.dispatchEvent(new Event('input',{bubbles:true}));
      }
    };
    fill('caseCompanyRuc',extracted.rucReceptor);
    fill('caseCompanyName',extracted.empresa);
    fill('caseProviderRuc',extracted.proveedorRuc);
    fill('caseProvider',extracted.proveedor);
    fill('caseDate',extracted.fecha);
    fill('caseServiceDate',extracted.fecha);
    fill('caseReceiverRuc',extracted.rucReceptor);
    fill('caseNumber',extracted.numero);
    fill('caseConcept',extracted.concepto);
    fill('caseTaxBase',extracted.baseImponible);
    fill('caseIGV',extracted.igv);
    fill('caseAmount',extracted.importeTotal||'');
    const voucher=$('#caseVoucherType');
    const voucherOption=[...voucher.options].find(option=>option.value.toLowerCase()===String(extracted.tipoComprobante||'').toLowerCase());
    if(voucherOption)voucher.value=voucherOption.value;
    const currency=$('#caseCurrency');
    const currencyOption=[...currency.options].find(option=>option.value===extracted.moneda);
    if(currencyOption)currency.value=currencyOption.value;
    const warnings=result.documents.filter(document=>document.warning).map(document=>`${document.name}: ${document.warning}`);
    const summary=result.documents.map(document=>`<li><b>${esc(document.name)}</b> · ${Object.values(document.datosExtraidos||{}).filter(Boolean).length} campo(s) detectado(s)${document.warning?` · ${esc(document.warning)}`:''}</li>`).join('');
    preview.innerHTML=`<div class="notice"><b>Extracción lista. Revisa los campos completados.</b><ul>${summary}</ul>${warnings.length?'<p>La lectura puede requerir instalación/configuración de OCR.</p>':''}</div>`;
    invalidateExpenseEvaluation();
  }catch(error){
    state.pendingExpenseFiles=[];
    preview.innerHTML=`<div class="notice">No se pudo leer el documento: ${esc(error.message)}. Verifica el archivo e inténtalo nuevamente.</div>`;
    toast(error.message);
  }
}
async function receiptFiles(files){
  const list=[...files],companyRuc=$('#receiptReceiverRuc')?.value.trim()||'';
  if(!list.length)return;
  if(!isValidRuc(companyRuc)){toast('Ingresa un RUC de empresa válido para asociar los comprobantes.');return}
  if(list.length>10){toast('Adjunta hasta 10 documentos por carga.');return}
  const preview=$('#receiptPreview');
  preview.innerHTML='<div class="notice">Leyendo y guardando documentos…</div>';
  const saved=[];
  const errors=[];
  for(const file of list){
    try{
      const form=new FormData();
      form.append('document',file,file.name);
      form.append('companyRuc',companyRuc);
      const document=await apiRequest('/api/documents',{method:'POST',body:form});
      const data=document.datosExtraidos||{};
      document.company=data.proveedor||'';
      document.proveedorRuc=data.proveedorRuc||'';
      document.receiver=data.rucReceptor||'';
      document.status='Pendiente de consulta oficial SUNAT';
      if(data.rucReceptor&&data.rucReceptor!==companyRuc)document.status='RUC receptor extraído no coincide';
      state.receipts.unshift(document);
      saved.push(document);
    }catch(error){errors.push(`${file.name}: ${error.message}`)}
  }
  if(!await saveReceipts())errors.push('Los comprobantes se subieron, pero no se pudo actualizar su historial.');
  const history=$('#receiptHistoryRows');
  if(history)history.innerHTML=receiptHistoryRows();
  preview.innerHTML=`<div class="notice">${saved.length} documento(s) guardado(s). El contenido extraído se propone como dato y no valida el CPE ante SUNAT.${errors.length?`<ul>${errors.map(error=>`<li>${esc(error)}</li>`).join('')}</ul>`:''}</div>`;
}
if($('#receiptFiles'))$('#receiptFiles').onchange=e=>receiptFiles(e.target.files);if($('#receiptDrop')){$('#receiptDrop').ondragover=e=>{e.preventDefault()};$('#receiptDrop').ondrop=e=>{e.preventDefault();receiptFiles(e.dataTransfer.files)}}
if($('#bulkExcel'))$('#bulkExcel').onchange=e=>readBulkExcel(e.target.files[0]);if($('#bulkDrop')){$('#bulkDrop').ondragover=e=>e.preventDefault();$('#bulkDrop').ondrop=e=>{e.preventDefault();readBulkExcel(e.dataTransfer.files[0])}}
if($('#downloadBulkTemplate'))$('#downloadBulkTemplate').onclick=()=>location.href='/api/expense-template.xlsx';
}
function filteredCaseItems(){
  const query=$('#caseSearch')?.value.toLowerCase()||'';
  const classification=$('#caseFilter')?.value||'';
  const period=$('#casePeriodFilter')?.value||'';
  const companyRuc=$('#matrixCompanyFilter')?.value||'';
  return state.cases.filter(item=>
    (!query||[item.empresa,item.empresaRuc,item.ruc,item.id,item.concepto,item.proveedor,item.proveedorRuc,item.numero].some(value=>String(value||'').toLowerCase().includes(query)))&&
    (!companyRuc||String(item.empresaRuc||item.ruc||'')===companyRuc)&&
    (!classification||caseEvaluation(item).status===classification)&&
    (!period||String(item.fecha||'').startsWith(period))
  );
}
function filterCases(){
  state.matrixPage=0;
  const items=filteredCaseItems(),cards=$('#matrixStatusCards');
  if(cards)cards.innerHTML=matrixStatusCards(items);
  renderMatrixContent(items);
}
function wireMatrixContent(root){
  wireCaseActions(root);
  root.querySelectorAll('[data-matrix-page]').forEach(button=>button.onclick=()=>{
    if(button.disabled)return;
    state.matrixPage=Number(button.dataset.matrixPage)||0;
    renderMatrixContent(filteredCaseItems());
  });
  const exportButton=root.querySelector('#exportCases');
  if(exportButton)exportButton.onclick=()=>exportMatrix(filteredCaseItems(),'matriz_gastos_empresariales.xlsx');
}
function renderMatrixContent(items){
  const root=$('#matrixContent');
  if(!root)return;
  root.innerHTML=matrixDashboard(items);
  wireMatrixContent(root);
}
function companyFilteredCaseItems(){
  const group=companyGroups().find(item=>item.key===state.selectedCompanyRuc);
  if(!group)return [];
  const period=$('#companyPeriodFilter')?.value||'';
  const classification=$('#companyClassFilter')?.value||'';
  return group.cases.filter(item=>
    (!period||String(item.fecha||'').startsWith(period))&&
    (!classification||caseEvaluation(item).status===classification)
  );
}
function filterCompanyCases(){
  const list=$('#companyCaseList'),items=companyFilteredCaseItems();
  if(!list)return;
  list.innerHTML=caseTable(items);
  wireCaseActions(list);
}
$('#globalSearch').addEventListener('keydown',e=>{if(e.key==='Enter'){let q=e.target.value.toLowerCase();if(q.includes('empresa'))go('empresas');else if(q.includes('gasto'))go('nuevo');else if(q.includes('comprobante'))go('comprobantes');else if(q.includes('caso')||q.includes('historial'))go('casos');else if(q.includes('norma')||q.includes('causalidad')||q.includes('fehaciencia'))go('guia');else toast('Busca empresas, gastos, comprobantes, casos o normativa.')}})
// La pantalla de autenticación se muestra primero; el usuario entra al pulsar Iniciar sesión.

function readBulkExcel(file){
  if(!file)return;
  if(!/\.xlsx?$/i.test(file.name)){toast('Selecciona un archivo .xlsx o .xls');return}
  $('#bulkPreview').innerHTML='<div class="notice">Leyendo encabezados, operaciones y posibles duplicados…</div>';
  (async()=>{
    try{
      let uploadFile=file,uploadName=file.name;
      if(/\.xls$/i.test(file.name)){
        if(!window.XLSX)throw new Error('Para convertir archivos .xls se necesita cargar SheetJS; inténtalo con Internet activo o guarda el archivo como .xlsx.');
        const workbook=XLSX.read(await file.arrayBuffer(),{type:'array',cellDates:true});
        if(!workbook.SheetNames.length)throw new Error('El archivo no contiene hojas de cálculo.');
        const converted=XLSX.write(workbook,{bookType:'xlsx',type:'array'});
        uploadFile=new Blob([converted],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
        uploadName=file.name.replace(/\.xls$/i,'.xlsx');
      }
      const form=new FormData();
      form.append('file',uploadFile,uploadName);
      const parsed=await apiRequest('/api/expense-import-preview',{method:'POST',body:form});
      showBulkPreview(file,parsed);
    }catch(error){
      console.error('No se pudo interpretar el archivo Excel.',error);
      $('#bulkPreview').innerHTML=`<div class="notice">${esc(error.message||'No se pudo leer el archivo. Revisa los encabezados y el formato.')}</div>`;
    }
  })();
}

function importKeyPart(value){return String(value??'').trim().toUpperCase().replace(/\s+/g,'')}
function importDocumentKeyPart(value){
  const text=importKeyPart(value);
  return /^\d+$/.test(text)?text.replace(/^0+(?=\d)/,''):text;
}
function hasImportRuc(value){return /^\d{11}$/.test(String(value??'').trim())}
function importTypeKey(value){
  const text=importKeyPart(value);
  const labels={'01':'FACTURA','03':'BOLETADEVENTA','04':'LIQUIDACIONDECOMPRA','07':'NOTADECREDITO','08':'NOTADEBITO','12':'TICKETDEMAQUINAREGISTRADORA','14':'RECIBODESERVICIOSPUBLICOS'};
  return labels[text]||text.normalize('NFD').replace(/[\u0300-\u036f]/g,'');
}
function makeImportDedupeKey(row){
  if(row.dedupeKey)return row.dedupeKey;
  const company=importKeyPart(row.companyRuc),period=String(row.period||row.fecha||'').replace(/\D/g,'').slice(0,6);
  const type=importTypeKey(row.codigoTipoComprobante||row.tipoComprobante);
  const supplier=importKeyPart(row.providerRuc);
  let series=importDocumentKeyPart(row.series),number=importDocumentKeyPart(row.voucherNumber);
  if(!number&&row.numero){
    const split=String(row.numero).split('-');
    if(!series&&split.length>1)series=importDocumentKeyPart(split[0]);
    number=importDocumentKeyPart(split.length>1?split.slice(1).join('-'):row.numero);
  }
  return company&&period&&type&&series&&number&&supplier?[company,period,type,series,number,supplier].join('|'):'';
}
function showBulkPreview(file,parsed){
  const errors=Array.isArray(parsed.errors)?parsed.errors:[];
  const seen=new Set();
  state.cases.forEach(item=>{
    const key=makeImportDedupeKey({
      dedupeKey:item.sireDedupeKey,companyRuc:item.empresaRuc||item.ruc,period:item.sirePeriod,
      fecha:item.fecha,codigoTipoComprobante:item.codigoTipoComprobante,tipoComprobante:item.tipoComprobante,
      series:item.serieSIRE,numero:item.numeroSIRE||item.numero,providerRuc:item.proveedorRuc
    });
    if(key)seen.add(key);
  });
  const rows=(parsed.operations||[]).map(operation=>{
    const row={
      row:operation.row,companyRuc:String(operation.companyRuc||'').trim(),companyName:String(operation.companyName||'').trim(),
      companyActivity:String(operation.companyActivity||'').trim(),companyActivitySecundaria1:'',companyActivitySecundaria2:'',
      fecha:operation.fecha||'',fechaServicio:operation.fechaServicio||'',fechaVencimientoPago:operation.fechaVencimientoPago||'',
      providerRuc:String(operation.supplierRuc||'').trim(),provider:String(operation.supplierName||'').trim(),
      tipoOperacion:operation.operationType|| (parsed.isSire?'Registro de compras SIRE':'Gasto empresarial'),
      codigoTipoComprobante:operation.codigoTipoComprobante||'',tipoComprobante:operation.tipoComprobante||'',
      tipoDocumentoIdentidadProveedor:operation.tipoDocumentoIdentidadProveedor||'',
      series:operation.series||'',voucherNumber:operation.voucherNumber||'',numero:operation.number||'',
      receiverRuc:operation.receiverRuc||'',concepto:operation.detailedDescription||'',
      descripcionDetalladaGasto:operation.detailedDescription||'',descripcion:operation.purpose||'',
      evidencia:operation.evidence||'',moneda:operation.currency||'PEN',base:Number(operation.base||0),igv:Number(operation.igv||0),
      total:Number(operation.total||0),reference:Number(operation.referenceAmount||0),income:Number(operation.annualNetIncome||0),
      paymentMethod:operation.paymentMethod||'',paymentReference:operation.paymentReference||'',
      sirePeriod:operation.period||'',sireCAR:operation.car||'',sireFields:operation.sireFields||[],
      amountBreakdown:operation.amountBreakdown||{},dedupeKey:operation.dedupeKey||'',contextMatched:Boolean(operation.contextMatched),
      duplicateWithinFile:Boolean(operation.duplicateWithinFile),issues:[...(operation.issues||[])]
    };
    if(!hasImportRuc(row.companyRuc))row.issues.push('RUC de empresa ausente o con formato inválido; esta fila no se importará.');
    else if(!isValidRuc(row.companyRuc))row.issues.push('El RUC de empresa no supera el dígito verificador; la evaluación quedará pendiente.');
    if(row.providerRuc&&!isValidRuc(row.providerRuc))row.issues.push('El RUC o documento del proveedor requiere verificación.');
    const key=makeImportDedupeKey(row);
    row.dedupeKey=key;
    row.duplicate=row.duplicateWithinFile||Boolean(key&&seen.has(key));
    if(row.duplicate&&!row.duplicateWithinFile)errors.push({row:row.row,message:'Posible comprobante duplicado en el historial; se omitirá.'});
    if(key)seen.add(key);
    row.importable=hasImportRuc(row.companyRuc)&&!row.duplicate;
    return row;
  });
  const identifiedCompanies=[...new Set(rows.filter(row=>hasImportRuc(row.companyRuc)).map(row=>row.companyRuc))];
  const duplicateCount=rows.filter(row=>row.duplicate).length;
  const importableCount=rows.filter(row=>row.importable).length;
  window._bulkRows=rows;
  const readingErrors=errors.filter(error=>!String(error.message||'').toLowerCase().includes('duplicado'));
  const errorList=readingErrors.length?`<details class="import-error-list"><summary>${readingErrors.length} error(es) de lectura</summary><ul>${readingErrors.slice(0,50).map(error=>`<li>${error.row?`Fila ${error.row}: `:''}${esc(error.message)}</li>`).join('')}</ul></details>`:'';
  const body=rows.slice(0,200).map((row,index)=>`<tr class="${row.duplicate?'import-duplicate-row':''}"><td>${row.row}</td><td>${esc(row.companyName||'Nombre pendiente')}<small class="table-subtext">${esc(row.companyRuc||'RUC no identificado')}</small></td><td>${esc(row.tipoComprobante||'—')} ${esc(row.numero||'')}</td><td><label class="import-description-field">Descripción detallada<textarea data-bulk-description="${index}" rows="1" placeholder="Completa el bien o servicio">${esc(row.descripcionDetalladaGasto)}</textarea></label><details class="import-purpose-details"><summary>${row.descripcion?'Ver o editar finalidad':'Añadir finalidad (opcional)'}</summary><label class="import-description-field">Finalidad empresarial<textarea data-bulk-purpose="${index}" rows="2" placeholder="Describe el uso del gasto, si lo conoces">${esc(row.descripcion)}</textarea></label></details></td><td>${esc(row.moneda)} ${Number(row.total||0).toLocaleString('es-PE',{minimumFractionDigits:2,maximumFractionDigits:2})}</td><td>${row.duplicate?'<span class="import-status-chip duplicate">Duplicado</span>':row.issues.length?`<details class="import-row-issues"><summary>${row.issues.length} dato(s) por verificar</summary><ul>${row.issues.map(issue=>`<li>${esc(issue)}</li>`).join('')}</ul></details>`:'<span class="import-status-chip ready">Lista para evaluar</span>'}</td></tr>`).join('');
  const matchedContext=rows.some(row=>row.contextMatched);
  const allDuplicates=rows.length>0&&duplicateCount===rows.length;
  const duplicateNotice=allDuplicates?'<div class="notice import-duplicates-summary">Estas operaciones ya aparecen en tu historial o están repetidas dentro del archivo; por eso no se volverán a importar.</div>':'';
  $('#bulkPreview').innerHTML=`<div class="section-head"><h2>Vista previa: ${esc(file.name)}</h2><span class="pill">${rows.length} operaciones leídas</span></div><div class="stats"><div class="stat"><small>Empresas identificadas</small><strong>${identifiedCompanies.length}</strong></div><div class="stat"><small>Operaciones para importar</small><strong>${importableCount}</strong></div><div class="stat"><small>Posibles duplicados</small><strong>${duplicateCount}</strong></div><div class="stat"><small>Errores de lectura</small><strong>${readingErrors.length}</strong></div></div><div class="notice">Hoja detectada: ${esc(parsed.sheetName||'—')} · ${parsed.isSire?`${parsed.headerCount} encabezados reconocidos; se conservarán también las demás columnas SIRE.`:'formato de Tribuanálisis reconocido.'} ${matchedContext?'La hoja «Contexto de casos» se relacionó con operaciones.':'Si existe una hoja «Contexto de casos», se relaciona por empresa, periodo, comprobante y RUC proveedor.'} Los datos faltantes no se presumen; cada clasificación la calcula la aplicación.</div>${duplicateNotice}${errorList}<div class="table-wrap bulk-preview-table-wrap"><table><thead><tr><th>Fila</th><th>Empresa / RUC</th><th>Comprobante</th><th>Información complementaria</th><th>Importe</th><th>Estado de lectura</th></tr></thead><tbody>${body||'<tr><td colspan="6">No se encontraron operaciones.</td></tr>'}</tbody></table></div>${rows.length>200?`<p class="footer-note">La vista muestra las primeras 200 operaciones; la importación considera las ${rows.length} filas leídas.</p>`:''}<button class="btn primary" id="importBulkRows" ${importableCount?'':'disabled'}>Importar ${importableCount} operación(es) y evaluar</button>`;
  $$('[data-bulk-description]').forEach(input=>input.oninput=()=>{const row=window._bulkRows[Number(input.dataset.bulkDescription)];if(row){row.descripcionDetalladaGasto=input.value;row.concepto=input.value}});
  $$('[data-bulk-purpose]').forEach(input=>input.oninput=()=>{const row=window._bulkRows[Number(input.dataset.bulkPurpose)];if(row)row.descripcion=input.value});
  $('#importBulkRows').onclick=async event=>{
    const button=event.currentTarget;
    button.disabled=true;
    const originalCases=state.cases,originalCompanies=state.companies;
    const importRows=window._bulkRows.filter(row=>row.importable);
    const status=$('#bulkPreview .notice');
    if(status)status.textContent='Consultando los RUC de empresa disponibles; si el servicio no responde, la importación seguirá con los datos existentes.';
    const rucs=[...new Set(importRows.map(row=>row.companyRuc).filter(isValidRuc))];
    const enrichment=await Promise.all(rucs.map(async ruc=>{
      try{
        const response=await fetch(`/api/ruc/${encodeURIComponent(ruc)}`);
        const data=await response.json();
        if(!response.ok)throw new Error(data.error||'Consulta no disponible');
        return [ruc,data];
      }catch(error){return [ruc,{lookupError:error instanceof Error?error.message:'Consulta no disponible'}]}
    }));
    const lookupByRuc=new Map(enrichment);
    const importForm=new FormData();
    importForm.append('file',file,file.name);
    let batch;
    try{batch=await apiRequest('/api/case-batches',{method:'POST',body:importForm})}
    catch(error){button.disabled=false;toast(`No se pudo archivar el Excel: ${error.message}`);return}
    const companyMap=new Map(originalCompanies.map(company=>[String(company.ruc),company]));
    importRows.forEach(row=>{
      const previous=companyMap.get(row.companyRuc)||{};
      const lookup=lookupByRuc.get(row.companyRuc)||{};
      const name=row.companyName||lookup.razonSocial||previous.name||'';
      const activity=row.companyActivity||lookup.actividadEconomicaPrincipal||lookup.actividadEconomica||previous.activity||'';
      const status=[lookup.estado,lookup.condicion].filter(Boolean).join(' · ');
      if(name&&isValidRuc(row.companyRuc)){
        companyMap.set(row.companyRuc,{
          ...previous,ruc:row.companyRuc,name,activity,
          actividadEconomicaPrincipal:activity,
          actividadEconomicaSecundaria1:lookup.actividadEconomicaSecundaria1||previous.actividadEconomicaSecundaria1||'',
          actividadEconomicaSecundaria2:lookup.actividadEconomicaSecundaria2||previous.actividadEconomicaSecundaria2||'',
          codigoCIIU:lookup.codigoCIIU||previous.codigoCIIU||'',
          sunatStatus:status||previous.sunatStatus||'',
          rucLookupSource:lookup.source||previous.rucLookupSource||'',
          rucLookupDate:lookup.consultedAt||previous.rucLookupDate||'',
          rucLookupOfficial:lookup.official===true
        });
      }
    });
    const timestamp=Date.now();
    const imported=importRows.map((row,index)=>{
      const lookup=lookupByRuc.get(row.companyRuc)||{};
      const company=companyMap.get(row.companyRuc)||{};
      const description=row.descripcionDetalladaGasto||row.concepto||'';
      return {
        id:`CAS-${timestamp}-${row.row}-${index}`,
        loteExcel:{id:batch.id,nombre:batch.name,fecha:batch.date,fila:row.row},
        empresa:row.companyName||lookup.razonSocial||company.name||'',empresaRuc:row.companyRuc,ruc:row.companyRuc,
        empresaActividad:row.companyActivity||lookup.actividadEconomicaPrincipal||lookup.actividadEconomica||company.activity||'',
        empresaActividadSecundaria1:lookup.actividadEconomicaSecundaria1||company.actividadEconomicaSecundaria1||'',
        empresaActividadSecundaria2:lookup.actividadEconomicaSecundaria2||company.actividadEconomicaSecundaria2||'',
        empresaCodigoCIIU:lookup.codigoCIIU||company.codigoCIIU||'',
        empresaRucStatus:lookup.lookupError?`Consulta externa pendiente: ${lookup.lookupError}`:
          [lookup.estado,lookup.condicion].filter(Boolean).join(' · ')||company.sunatStatus||'Estado y condición no disponibles',
        empresaRucFuente:lookup.source||company.rucLookupSource||'',
        empresaRucFechaConsulta:lookup.consultedAt||company.rucLookupDate||'',
        fecha:row.fecha,fechaServicio:row.fechaServicio,fechaVencimientoPago:row.fechaVencimientoPago,
        proveedor:row.provider,proveedorRuc:row.providerRuc,rucReceptor:row.receiverRuc,
        numero:row.numero,serieSIRE:row.series,numeroSIRE:row.voucherNumber,codigoTipoComprobante:row.codigoTipoComprobante,
        tipoDocumentoIdentidadProveedor:row.tipoDocumentoIdentidadProveedor,
        tipoOperacion:row.tipoOperacion,tipoComprobante:row.tipoComprobante,concepto:description,
        descripcionDetalladaGasto:description,descripcion:row.descripcion,evidencia:row.evidencia,
        moneda:row.moneda,monto:row.total,baseImponible:row.base,igv:row.igv,
        importeReferencia:row.reference,ingresosNetosAnuales:row.income,
        medioPago:row.paymentMethod,referenciaPago:row.paymentReference,
        sirePeriod:row.sirePeriod,sireCAR:row.sireCAR,sireDedupeKey:row.dedupeKey,
        sireFields:row.sireFields,amountBreakdown:row.amountBreakdown,contextMatched:row.contextMatched,
        validacionComprobante:row.sireCAR?'CAR informado; validación oficial pendiente':'CAR SUNAT no informado; validación oficial pendiente',
        origen:'Importación Excel',importObservations:row.issues
      };
    });
    state.companies=[...companyMap.values()];
    state.cases=[...imported,...originalCases];
    if(!await saveCases()){
      state.cases=originalCases;state.companies=originalCompanies;
      await saveWorkspace();
      let cleanupWarning='';
      try{await apiRequest(`/api/expense-batches/${encodeURIComponent(batch.id)}`,{method:'DELETE'})}
      catch(error){console.error('No se pudo limpiar el archivo Excel cuyo historial no se guardó.',error);cleanupWarning=` No se pudo limpiar el archivo: ${error.message}`}
      button.disabled=false;
      toast(`No se guardaron las filas; revisa la conexión con la base de datos.${cleanupWarning}`);
      return;
    }
    const counts={deducible:0,no_deducible:0,limitado:0,condicionado:0};
    const importedIds=new Set(imported.map(item=>item.id));
    state.cases.filter(item=>importedIds.has(item.id)).forEach(item=>{
      const key=caseEvaluation(item).status;
      if(Object.prototype.hasOwnProperty.call(counts,key))counts[key]++;
    });
    const queryFailures=[...lookupByRuc.values()].filter(item=>item.lookupError).length;
    const issues=errors.filter(error=>!String(error.message||'').toLowerCase().includes('duplicado')).length;
    toast(`${imported.length} operaciones guardadas en ${identifiedCompanies.length} empresa(s). Duplicados omitidos: ${duplicateCount}. Errores de lectura: ${issues}. Clasificación: ${counts.deducible} deducibles, ${counts.no_deducible} no deducibles, ${counts.limitado} limitados y ${counts.condicionado} condicionados.${queryFailures?` Consultas RUC pendientes: ${queryFailures}.`:''}`);
    go('casos');
  };
}
