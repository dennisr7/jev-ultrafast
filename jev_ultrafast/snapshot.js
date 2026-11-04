(() => {
  if (!document.body) return null;
  const cache = window.__jevFast ||= {ids:new WeakMap(), nodes:new Map(), next:1};
  const identity = e => {
    if (!cache.ids.has(e)) cache.ids.set(e,cache.next++);
    const id=cache.ids.get(e); cache.nodes.set(id,e); return id;
  };
  for (const [id,e] of cache.nodes) if (!e.isConnected) cache.nodes.delete(id);
  const safe = e => !['password','file','hidden'].includes(e.type);
  const visible = e => !e.closest('[aria-hidden="true"],[inert]') &&
    e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true});
  const name = (e,seen=new Set()) => {
    if (!e || seen.has(e)) return '';
    seen.add(e);
    const referenced=(e.getAttribute('aria-labelledby')||'').split(/\s+/)
      .map(id=>name(document.getElementById(id),seen)).filter(Boolean).join(' ');
    return referenced || e.getAttribute('aria-label') ||
      [...(e.labels||[])].map(l=>name(l,seen)).filter(Boolean).join(' ') ||
      (['button','submit','reset'].includes(e.type) ? e.value : '') || e.getAttribute('alt') ||
      (e.tagName==='INPUT' ? '' : [...e.childNodes].map(n=>n.nodeType===3 ? n.textContent :
        n.nodeType===1 && n.getAttribute('aria-hidden')!=='true' ? name(n,seen) : '').join(' ').trim()) ||
      e.getAttribute('title') || e.getAttribute('placeholder') || '';
  };
  const roles=['button','link','checkbox','radio','switch','tab','menuitem','menuitemradio',
    'option','gridcell','combobox','textbox','searchbox','spinbutton'];
  const selector='a[href],button,input,textarea,select,summary,[contenteditable="true"],'+
    roles.map(role=>'[role="'+role+'"]').join(',');
  const role = e => {
    const explicit=e.getAttribute('role');
    if (roles.includes(explicit)) return explicit;
    if (e.tagName==='BUTTON' || e.tagName==='SUMMARY') return 'button';
    if (e.tagName==='A') return 'link';
    if (e.tagName==='SELECT') return 'combobox';
    if (e.tagName==='TEXTAREA' || e.isContentEditable) return 'textbox';
    if (e.tagName==='INPUT') {
      if (['checkbox','radio'].includes(e.type)) return e.type;
      if (['button','submit','reset','image'].includes(e.type)) return 'button';
      if (e.type==='search') return 'searchbox';
      if (e.type==='number') return 'spinbutton';
      if (['text','email','url','tel'].includes(e.type)) return 'textbox';
    }
    return null;
  };
  cache.pageKey=()=>[performance.timeOrigin,location.href,scrollX,scrollY,innerWidth,innerHeight,
    [...document.querySelectorAll('input,textarea,select')].filter(safe)
      .map(e=>[identity(e),e.value,e.checked,e.selectedIndex,e.disabled,e.readOnly])];
  cache.guard=e=>{
    if (!e?.isConnected || !visible(e)) return null;
    const scope=e.closest('form,dialog,[role="dialog"],article,li,tr,[role="row"]') || e.parentElement;
    return [identity(e),role(e),name(e),e.value??null,e.checked??null,e.selectedIndex??null,
      e.readOnly??null,e.matches(':disabled'),e.getAttribute('aria-disabled'),
      e.getAttribute('aria-expanded'),e.getAttribute('aria-checked'),e.getAttribute('aria-selected'),
      e.getAttribute('href'),scope?.innerText?.slice(0,6000)||''];
  };
  // Whole-page checklist: required fields anywhere on the page, in view or not, that are still empty.
  // Custom dropdowns (react-select) show a placeholder until a value is chosen.
  // The chosen value of a custom dropdown, '' while it shows its placeholder, null if not one.
  const chosen=e=>{
    const answer='[class*="single-value"],[class*="multi-value"]', hint='[class*="placeholder"]';
    let box=e;
    for (let i=0;i<4 && box.parentElement && !box.querySelector(answer+','+hint);i++) box=box.parentElement;
    // Each chosen option of a multi-select has an outer box and an inner label: read only one of them, once.
    const labels=box.querySelectorAll('[class*="single-value"],[class*="multi-value__label"]');
    const picked=[...new Set([...(labels.length ? labels : box.querySelectorAll(answer))]
      .map(x=>x.innerText.trim()).filter(Boolean))];
    return picked.length ? picked.join(', ') : box.querySelector(hint) ? '' : null;
  };
  const empty=e=>{
    if (['radio','checkbox'].includes(e.type))
      return ![...(e.name ? document.getElementsByName(e.name) : [e])].some(x=>x.checked);
    if (e.tagName==='SELECT') return !e.value;
    const picked=e.getAttribute('role')==='combobox' ? chosen(e) : null;
    return picked!==null ? !picked : !String(e.value??'').trim();
  };
  const required=[], optional=[], groups=new Set();
  for (const e of document.querySelectorAll('input,textarea,select,[role="combobox"]')) {
    if (!safe(e) || e.matches(':disabled')) continue;
    if (!(e.required || e.getAttribute('aria-required')==='true')) {
      // Empty optional text fields and dropdowns (e.g. Website): listed so a goal that fills one can see it exists.
      if (['radio','checkbox'].includes(e.type) || optional.length>=30) continue;
      // Never surface voluntary self-identification (EEO) questions: goals must not touch them.
      if (e.closest('[class*="eeoc"],[id*="eeoc"],[class*="demographic"]')) continue;
      const shell=e.getAttribute('role')==='combobox' && (e.closest('[class*="control"]') || e.parentElement);
      if (!visible(e) && !(shell && visible(shell))) continue;
      const label=name(e).replace(/\s*\*\s*$/,'').trim();
      if (!label || !empty(e) || e.type==='search') continue;
      const r=e.getBoundingClientRect();
      optional.push({node:identity(e),label:label.slice(0,120),
        where:r.bottom<0 ? 'above' : r.top>innerHeight ? 'below' : 'in view'});
      continue;
    }
    // Choice inputs and custom dropdowns hide the input itself (a dropdown's text box turns transparent once
    // a value is chosen), so judge those by their label or visible box instead.
    const shell=e.getAttribute('role')==='combobox' && (e.closest('[class*="control"]') || e.parentElement);
    if (!visible(e) && !(shell && visible(shell)) &&
        !(['radio','checkbox'].includes(e.type) && e.labels?.[0] && visible(e.labels[0]))) continue;
    if (e.name && ['radio','checkbox'].includes(e.type)) { if (groups.has(e.name)) continue; groups.add(e.name); }
    const group=['radio','checkbox'].includes(e.type) && e.closest('fieldset,[role=group],[role=radiogroup]');
    const groupLabel=group ? (group.querySelector('legend')?.innerText || name(group) || '') : '';
    const label=(groupLabel || name(e)).replace(/\s+/g,' ').replace(/\s*\*\s*$/,'').trim();
    if (!label) continue;
    const r=e.getBoundingClientRect();
    const picked=e.getAttribute('role')==='combobox' ? chosen(e) : null;
    required.push({node:identity(e),label:label.slice(0,160),empty:empty(e),
      // Dropdown answers as chosen; typed fields only as "(filled)" so personal details are not repeated.
      answer:picked || (group ? [...group.querySelectorAll('input[type=checkbox]:checked,input[type=radio]:checked')]
        .map(c=>name(c).trim()).filter(Boolean).join(', ') || 'checked' :
        ['radio','checkbox'].includes(e.type) ? 'checked' : '(filled)'),
      where:r.bottom<0 ? 'above' : r.top>innerHeight ? 'below' : 'in view'});
  }
  const form={required:required.length,
    empty:required.filter(f=>f.empty).slice(0,30).map(({empty,answer,...f})=>f),
    answered:required.filter(f=>!f.empty).slice(0,40).map(f=>({label:f.label,answer:f.answer})),
    optional_empty:optional};
  const stillEmpty=new Set(form.empty.map(f=>f.node));
  const actions=[];
  for (const e of document.querySelectorAll(selector)) {
    if (!safe(e) || !visible(e) || e.matches(':disabled') || e.closest('[aria-disabled="true"]')) continue;
    const r=e.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2, rname=role(e);
    if (!rname || r.width<=0 || r.height<=0 || x<0 || y<0 || x>=innerWidth || y>=innerHeight) continue;
    if (rname==='gridcell' && e.querySelector('button,[role="button"]')) continue;
    const base={node:identity(e),role:rname,label:name(e)||rname,
      rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
    if (stillEmpty.has(base.node)) base.still_empty=true;
    for (const key of ['checked','selected','expanded']) {
      const value=e.getAttribute('aria-'+key);
      if (value!==null) base[key]=value;
    }
    if (['checkbox','radio'].includes(e.type)) base.checked=String(e.checked);
    if (e.tagName==='SELECT') {
      for (const o of e.options) if (!o.selected && !o.disabled && !o.closest('optgroup[disabled]'))
        actions.push({...base,kind:'select',value:o.value,
          current_value:[...e.selectedOptions].map(o=>o.label).join(', '),label:base.label+' → '+o.label});
    } else {
      const editable=!e.readOnly && e.getAttribute('aria-readonly')!=='true' &&
        (['textbox','searchbox','spinbutton'].includes(rname) ||
          (rname==='combobox' && ['INPUT','TEXTAREA'].includes(e.tagName)));
      const picked=rname==='combobox' ? chosen(e) : null;
      const value=picked ? picked : 'value' in e ? String(e.value) :
        e.isContentEditable || rname==='combobox' ? e.innerText.trim() : '';
      actions.push({...base,kind:editable?'fill':'click',value});
      if (editable) actions.push({...base,kind:'click',value,label:'Open '+base.label});
    }
  }
  const words=[], walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  const range=document.createRange(); let node,length=0;
  while ((node=walker.nextNode()) && length<6000) {
    const value=node.textContent.trim(), parent=node.parentElement;
    if (!value || !parent || parent.closest('script,style,noscript,template') || !visible(parent)) continue;
    range.selectNodeContents(node); const r=range.getBoundingClientRect();
    if (r.width>0 && r.height>0 && r.bottom>0 && r.top<innerHeight && r.right>0 && r.left<innerWidth) {
      words.push(value); length+=value.length;
    }
  }
  const text=words.join('\n').slice(0,6000), height=document.documentElement.scrollHeight;
  const page_key=cache.pageKey(), guards={};
  for (const a of actions) if (!(a.node in guards)) guards[a.node]=cache.guard(cache.nodes.get(a.node));
  // Compare meaning and identity. Geometry is always resolved and hit-tested just before input.
  const semantics=actions.map(({rect,...action})=>action);
  const marker=[performance.timeOrigin,location.href,scrollX,scrollY,innerWidth,innerHeight,
    document.title,text,semantics,page_key[6]];
  const omitted_actions=Math.max(0,actions.length-250);
  actions.splice(250);
  actions.forEach((a,i)=>a.id='e'+(i+1));
  // Jump forward to the next empty field below the view; fall back to one above only when none is below,
  // so a field left blank on purpose higher up cannot pull Jev back forever.
  const next=form.empty.find(f=>f.where==='below') || form.empty.find(f=>f.where==='above');
  // Offered only when no empty required field is in view: one in view should be answered (or skipped) first.
  if (next && !form.empty.some(f=>f.where==='in view'))
    actions.push({id:'next_empty_field',kind:'scroll_to',node:next.node,
      label:'Scroll to the next required field that is still empty: '+next.label+' ('+next.where+')'});
  // Jumps to empty optional fields are added in Python (model.focus_on_goal), which knows the goal.
  if (scrollY+innerHeight<height-2) actions.push({id:'scroll_down',kind:'scroll',label:'Scroll down',delta:560});
  if (scrollY>0) actions.push({id:'scroll_up',kind:'scroll',label:'Scroll up',delta:-560});
  actions.push({id:'wait',kind:'wait',label:'Wait for the page to update'});
  return {url:location.href,title:document.title,w:innerWidth,h:innerHeight,text,
    scroll:{y:scrollY,height},actions,form,marker,page_key,guards,omitted_actions};
})()
