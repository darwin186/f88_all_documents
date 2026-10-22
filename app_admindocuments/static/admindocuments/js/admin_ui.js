(() => {
  const names = {q:'Tìm kiếm',company:'Công ty',doc_type:'Loại văn bản',paper_type:'Loại giấy',department:'Phòng ban',recipient:'Người nhận',status:'Trạng thái',start_date:'Từ ngày',end_date:'Đến ngày',receive_location:'Nơi nhận',unnotified:'Chưa thông báo',unassigned:'Chưa có người nhận',year:'Năm',month:'Tháng'};
  const contextNames = new Set(['page','open','sort','dir','tab','pane','split_by_day','create','edit','csrfmiddlewaretoken']);
  const mounts = new WeakMap(), ranges = new WeakMap();
  let nextId = 0;
  const mountChips = (form, container, {values, remove}) => {
    if (mounts.has(container)) return mounts.get(container);
    const items = container.querySelector('[data-filter-chip-items]');
    const render = () => {
      const selected = values(); container.hidden = !selected.length;
      container.querySelector('[data-filter-count]').textContent = `${selected.length} bộ lọc đang chọn`; items.replaceChildren();
      selected.forEach(value => {
        const chip = document.createElement('span'); chip.className = 'adm-filter-chip';
        const label = document.createElement('span'); label.textContent = `${value.label}: ${value.value}`;
        const button = document.createElement('button'); button.type = 'button'; button.textContent = '×'; button.dataset.removeFilter = value.key; button.setAttribute('aria-label', `Bỏ bộ lọc ${value.label}`);
        chip.append(label, button); items.append(chip);
      });
    };
    container.addEventListener('click', event => { const button = event.target.closest('[data-remove-filter]'); if (button) remove(button.dataset.removeFilter); });
    form.addEventListener('input', render); form.addEventListener('change', render); mounts.set(container, render); render(); return render;
  };
  const chipContainer = () => {
    const root = document.createElement('div'); root.className = 'adm-filter-chips'; root.dataset.filterChips = ''; root.setAttribute('aria-live','polite'); root.hidden = true;
    const count = document.createElement('span'); count.dataset.filterCount = '';
    const items = document.createElement('div'); items.dataset.filterChipItems = ''; root.append(count,items); return root;
  };
  const enhanceSelects = root => {
    root.querySelectorAll('select:not([multiple]):not([size])').forEach(source => {
      if (source.closest('[data-document-select], [data-filter-select], [data-ui-select], [data-ui-native]')) return;
      if(!source.id)source.id=`adm-ui-field-${++nextId}`;
      const fieldLabel=source.parentElement.querySelector('label');
      if(fieldLabel&&!fieldLabel.htmlFor&&source.parentElement.querySelectorAll('input,select,textarea').length===1)fieldLabel.htmlFor=source.id;
      const wrapper = document.createElement('div'); wrapper.dataset.documentSelect = ''; wrapper.className = 'adm-ui-select';
      source.before(wrapper); wrapper.append(source);
      const toggle = document.createElement('button'); toggle.type='button'; toggle.dataset.selectToggle=''; toggle.hidden=true; toggle.setAttribute('aria-expanded','false');
      const label=document.createElement('span'); label.dataset.selectLabel=''; const arrow=document.createElement('span'); arrow.textContent='⌄'; arrow.setAttribute('aria-hidden','true'); toggle.append(label,arrow);
      const menu=document.createElement('div'); menu.dataset.selectMenu=''; menu.hidden=true; menu.id=`adm-ui-menu-${++nextId}`; toggle.setAttribute('aria-controls',menu.id);
      const clear=document.createElement('button'); clear.type='button'; clear.dataset.selectClear=''; clear.textContent='Bỏ chọn';
      const search=document.createElement('input'); search.type='search'; search.dataset.selectSearch=''; search.placeholder='Tìm kiếm…'; search.setAttribute('aria-label',`Tìm ${source.labels?.[0]?.textContent || names[source.name] || 'lựa chọn'}`);
      const options=document.createElement('ul'); options.dataset.selectOptions='';
      const empty=document.createElement('p'); empty.dataset.selectEmpty=''; empty.hidden=true; empty.textContent='Không tìm thấy kết quả';
      menu.append(clear,search,options,empty); wrapper.append(toggle,menu);
    });
    window.adminDocumentFormControls?.init(root);
  };
  const calendarOptions = input => ({locale:{...window.flatpickr.l10ns.vn,rangeSeparator:' → '},monthSelectorType:'static',disableMobile:true,allowInput:false,
    appendTo:input.closest('dialog') || document.body,
    onReady:(_,__,fp)=>fp.calendarContainer.classList.add('adm-filter-datepicker'),
    onOpen:(_,__,fp)=>document.querySelectorAll('input').forEach(other=>{if(other._flatpickr && other._flatpickr!==fp)other._flatpickr.close();other.datepicker?.hide();})});
  const enhanceDates = root => {
    if (!window.flatpickr) return;
    root.querySelectorAll('form[method=get], form[method=GET]').forEach(form=>{
      if (form.matches('[data-adm-filters]') || ranges.has(form)) return;
      const start=form.querySelector('input[name=start_date][type=date]'), end=form.querySelector('input[name=end_date][type=date]');
      if (!start || !end) return;
      const label=start.labels?.[0], endLabel=end.labels?.[0], endParent=end.parentElement;
      const visible=document.createElement('input'); visible.type='text'; visible.id=`adm-ui-range-${++nextId}`; visible.className='adm-ui-date'; visible.placeholder='Chọn khoảng ngày'; visible.autocomplete='off'; start.after(visible);
      if(label){label.textContent='Khoảng ngày';label.htmlFor=visible.id;}
      const defaults=[start.value,end.value].filter(Boolean).map(value=>new Date(`${value}T00:00:00`));
      start.type='hidden';end.type='hidden'; if(endLabel)endLabel.hidden=true;
      if(endParent!==form && endParent.querySelectorAll('input, select, button, a').length===1)endParent.hidden=true;
      const fp=window.flatpickr(visible,{...calendarOptions(visible),mode:'range',dateFormat:'d/m/Y',defaultDate:defaults,
        onChange:(dates,_,instance)=>{start.value=dates[0]?instance.formatDate(dates[0],'Y-m-d'):'';end.value=dates.length?instance.formatDate(dates[1]||dates[0],'Y-m-d'):'';form.dispatchEvent(new Event('change',{bubbles:true}));}});
      ranges.set(form,{start,end,fp});
    });
    root.querySelectorAll('input[type=date]:not([data-ui-native])').forEach(input=>{
      if(input._flatpickr)return; input.autocomplete='off'; input.classList.add('adm-ui-date');
      const label=input.labels?.[0];
      const fp=window.flatpickr(input,{...calendarOptions(input),dateFormat:'Y-m-d',altInput:true,altFormat:'d/m/Y',minDate:input.min||undefined,maxDate:input.max||undefined});
      fp.altInput.autocomplete='off';fp.altInput.classList.add('adm-ui-date');
      if(label){fp.altInput.id=`adm-ui-date-${++nextId}`;label.htmlFor=fp.altInput.id;}
      input.addEventListener('change',()=>{if(input.value!==fp.formatDate(fp.selectedDates[0]||new Date(0),'Y-m-d'))fp.setDate(input.value,false);});
    });
  };
  const fieldLabel = input => input.labels?.[0]?.textContent.replace(/\s*\*\s*$/,'').trim() || names[input.name] || input.placeholder || input.name;
  const enhanceFilters = root => root.querySelectorAll('form[method=get],form[method=GET]').forEach(form=>{
    if(form.matches('[data-adm-filters]') || form.dataset.sharedFilterReady)return;
    form.dataset.sharedFilterReady='1';form.classList.add('adm-ui-filter');
    const footer=form.querySelector('.adm-filter-footer') || document.createElement('div'); footer.className='adm-filter-footer adm-filter-footer-with-chips';
    const chips=footer.querySelector('[data-filter-chips]') || chipContainer(), actions=footer.querySelector('.adm-actions') || document.createElement('div');actions.className='adm-actions'; if(!chips.parentElement)footer.append(chips);if(!actions.parentElement)footer.append(actions);
    form.querySelectorAll('button[type=submit],button:not([type]),input[type=submit],button[type=reset]').forEach(button=>actions.append(button));
    form.querySelectorAll('a').forEach(link=>{if(/^(Đặt lại|Xóa bộ lọc|Bỏ lọc)$/i.test(link.textContent.trim())){link.classList.add('ui-btn','ui-btn-secondary');actions.append(link);}});
    if(!actions.querySelector('[type=submit]')){const button=document.createElement('button');button.type='submit';button.className='ui-btn ui-btn-primary';button.textContent='Áp dụng bộ lọc';actions.prepend(button);}
    if(!actions.querySelector('a')){
      const clear=document.createElement('a'), query=new URLSearchParams();clear.className='ui-btn ui-btn-secondary';clear.textContent='Xóa bộ lọc';
      ['tab','pane','split_by_day'].forEach(name=>{if(form.elements[name]?.value)query.set(name,form.elements[name].value);});
      const url=new URL(form.getAttribute('action')||location.href,location.href);url.search=query.toString();clear.href=url.href;actions.append(clear);
    }
    form.append(footer);
    actions.querySelectorAll('a').forEach(link=>{
      if(!/^(Đặt lại|Xóa bộ lọc|Bỏ lọc)$/i.test(link.textContent.trim()))return;
      link.textContent='Xóa bộ lọc';const url=new URL(link.href,location.href);
      ['tab','pane','split_by_day'].forEach(name=>{if(form.elements[name]?.value)url.searchParams.set(name,form.elements[name].value);});link.href=url.href;
    });
    const controls=()=>[...form.elements].filter(input=>input.name&&!contextNames.has(input.name)&&!input.disabled&&!['submit','button','reset','file'].includes(input.type));
    mountChips(form,chips,{values:()=>{
      const range=ranges.get(form), values=[];
      if(range&&(range.start.value||range.end.value))values.push({key:'__range',label:'Khoảng ngày',value:range.fp.input.value});
      controls().forEach(input=>{
        if(range&&(input===range.start||input===range.end))return;
        if(['checkbox','radio'].includes(input.type)&&!input.checked)return;
        if(!input.value || input.value==='all' || ['unnotified','unassigned'].includes(input.name)&&input.value==='0')return;
        values.push({key:input.name,label:fieldLabel(input),value:input.tagName==='SELECT'?input.selectedOptions[0]?.textContent:input._flatpickr?.altInput?.value || (['unnotified','unassigned'].includes(input.name)?'Có':input.value)});
      });return values;
    },remove:key=>{
      if(key==='__range'){const range=ranges.get(form);range.start.value='';range.end.value='';range.fp.clear(false);}
      else controls().filter(input=>input.name===key).forEach(input=>{if(['radio','checkbox'].includes(input.type))input.checked=false;else{input.value='';input._flatpickr?.clear(false);}input.dispatchEvent(new Event('change',{bubbles:true}));});
      form.dispatchEvent(new Event('change',{bubbles:true}));form.requestSubmit();
    }});
  });
  const enhancePresentation = root => {
    const legacy=root.closest('.adm-shared-page, .adm-public-page') || root.querySelector('.adm-shared-page, .adm-public-page');if(!legacy)return;
    root.querySelectorAll('table').forEach(table=>{
      table.classList.add('adm-ui-table');
      if(!table.parentElement.matches('.adm-table-scroll')){
        if(table.parentElement.matches('[class*=overflow]')&&table.parentElement.children.length===1)table.parentElement.classList.add('adm-table-scroll');
        else{const wrap=document.createElement('div');wrap.className='adm-table-scroll';table.before(wrap);wrap.append(table);}
      }
    });
    root.querySelectorAll('button, a').forEach(button=>{
      if(button.closest('[data-document-select], [data-filter-select], [data-ui-select], [data-ui-file], [data-ui-upload], [data-ui-combobox], .adm-pagination, [data-filter-chips]') || button.matches('[role=tab],[data-preview-tab],[data-paper-tab]'))return;
      if(button.tagName==='A'&&!/(?:px-|py-)/.test(button.className))return;
      if(button.closest('ul')&&!button.matches('[type=submit]'))return;
      button.classList.add('ui-btn');
      const text=button.textContent.trim();
      if(/^(×|✕|Đóng)$/.test(text)&&button.closest('[class*=fixed]'))button.classList.add('adm-ui-close');
      else if(/bg-(?:f88green|emerald-[567]00|green-[567]00|slate-900|gray-900)/.test(button.className))button.classList.add('ui-btn-primary');
      else if(/^(Xóa bộ lọc|Đặt lại|Hủy)$/.test(text))button.classList.add('ui-btn-secondary');
      else if(/text-red|bg-red/.test(button.className))button.classList.add('ui-btn-danger');
    });
    root.querySelectorAll('section.bg-white, div.bg-white[class*=shadow]').forEach(panel=>{if(!panel.closest('[data-document-select], [data-filter-select]'))panel.classList.add('adm-ui-panel');});
    root.querySelectorAll('span[class*=rounded][class*=text-]').forEach(badge=>{if(!/(?:w-|h-)/.test(badge.className)&&!badge.closest('[data-filter-chips]'))badge.classList.add('adm-ui-badge');});
    root.querySelectorAll('[id*=Modal], [id*=Drawer], [role=dialog]').forEach(dialog=>{
      if(dialog.tagName==='DIALOG'||!dialog.classList.contains('fixed'))return;dialog.classList.add(/Drawer/i.test(dialog.id)?'adm-ui-drawer':'adm-ui-modal');
    });
  };
  const enhance = root => {enhancePresentation(root);enhanceSelects(root);enhanceFilters(root);enhanceDates(root);root.querySelectorAll('[data-shared-filter-ready]').forEach(form=>form.dispatchEvent(new Event('change',{bubbles:true})));};
  window.adminUi={mountChips,enhance};
  document.addEventListener('DOMContentLoaded',()=>{
    const page=document.querySelector('.adm-page, .adm-public-page');if(!page)return;enhance(page);
    const observer=new MutationObserver(records=>{
      const added=new Set();records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===1&&!node.closest('[data-select-menu], [data-select-options], [data-filter-chips], .flatpickr-calendar, [data-filter-select]'))added.add(node.parentElement);}));
      added.forEach(root=>{if(root&&page.contains(root))enhance(root);});
    });observer.observe(page,{childList:true,subtree:true});
    document.addEventListener('show',event=>{if(event.target.datepicker)document.querySelectorAll('input').forEach(input=>input._flatpickr?.close());},true);
    const closeDates=()=>page.querySelectorAll('input').forEach(input=>input._flatpickr?.close());window.addEventListener('resize',closeDates);document.addEventListener('scroll',closeDates,true);
  });
})();
