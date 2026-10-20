document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-mail-merge-preview]');
  if (!root) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const icon = name => {
    const paths = {eye:'<path d="M2 8s2-5 6-5 6 5 6 5-2 5-6 5-6-5-6-5Z"/><circle cx="8" cy="8" r="2"/>',hidden:'<path d="m2 2 12 12M6.5 3.2 8 3c4 0 6 5 6 5l-1.4 2M9.5 12.8 8 13c-4 0-6-5-6-5l1.4-2"/>',lock:'<rect x="4" y="7" width="8" height="6" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>',search:'<circle cx="7" cy="7" r="4"/><path d="m10 10 4 4"/>',grid:'<rect x="2" y="2" width="12" height="12" rx="2"/><path d="M2 6h12M6 6v8"/>',download:'<path d="M8 2v8m-3-3 3 3 3-3M2 11v3h12v-3"/>',plus:'<path d="M8 2v12M2 8h12"/>',chevron:'<path d="m4 6 4 4 4-4"/>'};
    return `<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true">${paths[name] || paths.grid}</svg>`;
  };
  const initial = () => ({
    step: Number(new URLSearchParams(location.search).get('step')) || 3,
    name: 'Đối soát hồ sơ PGD · Tháng 10/2026', deadline: '2026-10-24T17:00',
    subject: '[{{report_month}}] Đề nghị {{shop_name}} đối soát hồ sơ',
    instructions: 'Vui lòng kiểm tra từng hồ sơ, chọn kết quả và bổ sung lý do nếu hồ sơ chưa đầy đủ.',
    file: 'Doi_soat_ho_so_T10_2026.xlsx', selected: 'response', gridView: 'team', shopFilter: 'all',
    mapping: {shop: 'shop_code', email: 'master'}, closed: false,
    columns: [
      {key:'shop_code',label:'Mã PGD',type:'text',source:true,visible:true},
      {key:'shop_name',label:'Phòng giao dịch',type:'text',source:true,visible:true},
      {key:'email',label:'Email PGD',type:'text',source:true,visible:false},
      {key:'contract',label:'Mã hợp đồng',type:'text',source:true,visible:true},
      {key:'customer',label:'Khách hàng',type:'text',source:true,visible:true},
      {key:'content',label:'Nội dung đối soát',type:'text',source:true,visible:true},
      {key:'response',label:'Kết quả phản hồi',type:'select',source:false,visible:true,required:true,options:['Đã đủ hồ sơ','Cần bổ sung','Không phát sinh']},
      {key:'comment',label:'Ghi chú PGD',type:'text',source:false,visible:true,required:false},
    ],
    shops: [
      {code:'BGG21012',name:'Ngã Ba Phúc Lâm',email:'bgg21012@example.com',delivery:'sent',status:'submitted'},
      {code:'YBI23007',name:'Dốc Đỏ Nghĩa Lộ',email:'ybi23007@example.com',delivery:'sent',status:'editing'},
      {code:'AGG20008',name:'120 Lý Thái Tổ',email:'agg20008@example.com',delivery:'pending',status:'pending'},
    ],
    rows: [
      {id:1,shop_code:'BGG21012',shop_name:'Ngã Ba Phúc Lâm',email:'bgg21012@example.com',contract:'60759475531001',customer:'Khách hàng mẫu 01',content:'Kiểm tra bộ hồ sơ hợp đồng',response:'Đã đủ hồ sơ',comment:''},
      {id:2,shop_code:'BGG21012',shop_name:'Ngã Ba Phúc Lâm',email:'bgg21012@example.com',contract:'60759475531002',customer:'Khách hàng mẫu 02',content:'Bổ sung biên bản bàn giao',response:'Cần bổ sung',comment:'PGD đang bổ sung hồ sơ'},
      {id:3,shop_code:'YBI23007',shop_name:'Dốc Đỏ Nghĩa Lộ',email:'ybi23007@example.com',contract:'60759475531003',customer:'Khách hàng mẫu 03',content:'Đối chiếu thông tin khách hàng',response:'',comment:''},
      {id:4,shop_code:'YBI23007',shop_name:'Dốc Đỏ Nghĩa Lộ',email:'ybi23007@example.com',contract:'60759475531004',customer:'Khách hàng mẫu 04',content:'Kiểm tra chữ ký trên hồ sơ',response:'',comment:''},
      {id:5,shop_code:'AGG20008',shop_name:'120 Lý Thái Tổ',email:'agg20008@example.com',contract:'60759475531005',customer:'Khách hàng mẫu 05',content:'Xác nhận hồ sơ đã bàn giao',response:'',comment:''},
      {id:6,shop_code:'AGG20008',shop_name:'120 Lý Thái Tổ',email:'agg20008@example.com',contract:'60759475531006',customer:'Khách hàng mẫu 06',content:'Kiểm tra bộ hồ sơ hợp đồng',response:'',comment:''},
    ],
  });
  const storageKey = 'f88-mail-merge-ui-preview-v1';
  const creating = new URLSearchParams(location.search).get('mode') === 'create';
  let state = initial();
  if(creating){state.name='';state.step=1;}
  let selectedShop = state.shops[0].code;
  let toastTimer;
  const content = root.querySelector('[data-step-content]');
  const dialog = root.querySelector('[data-mm-dialog]');
  const aliveColumns = () => state.columns.filter(column => !column.removed);
  const responseColumns = () => aliveColumns().filter(column => !column.source);
  const shopRows = code => state.rows.filter(row => code === 'all' || row.shop_code === code);
  const pill = (text, tone='') => `<span class="mm-label-pill ${tone}">${esc(text)}</span>`;
  const button = (action,label,primary=false,extra='') => `<button type="button" class="ui-btn ${primary?'ui-btn-primary':'ui-btn-secondary'}" data-action="${action}" ${extra}>${label}</button>`;
  const toast = message => {
    const box=root.querySelector('.mm-toast'); box.textContent=message;box.hidden=false;
    clearTimeout(toastTimer);toastTimer=setTimeout(()=>box.hidden=true,3800);
  };
  const stat = (label,value,detail) => `<div class="mm-stat"><span>${label}</span><strong>${value}</strong><small>${detail}</small></div>`;
  const sectionHead = (title,copy,actions='') => `<div class="mm-section-head"><div><h2>${title}</h2><p>${copy}</p></div><div class="mm-section-actions">${actions}</div></div>`;
  const field = (label,control,wide=false) => `<div class="mm-form-group ${wide?'wide':''}"><span class="mm-form-label">${label}</span>${control.replace(/<(input|select|textarea)\b/, '<$1 aria-label="'+esc(label)+'"')}</div>`;
  const formInput = (key,value,type='text') => `<input class="mm-input" data-config="${key}" value="${esc(value)}" type="${type}">`;
  const selectOptions = (items,value) => items.map(([key,label])=>`<option value="${esc(key)}" ${key===value?'selected':''}>${esc(label)}</option>`).join('');
  const typeOptions = [['text','Văn bản'],['select','Danh sách lựa chọn'],['number','Số'],['date','Ngày']];
  const toggle = (name,checked,disabled=false) => `<label class="mm-switch"><input type="checkbox" data-column-option="${name}" ${checked?'checked':''} ${disabled?'disabled':''} aria-label="${name==='visible'?'Hiện với PGD':'Bắt buộc trả lời'}"><span></span></label>`;
  function table(rows, columns, editable=false, summary=false) {
    return `<div class="mm-grid-scroll"><table class="mm-table"><thead><tr><th>STT</th>${columns.map(column=>`<th class="${!column.source?'response-column':''} ${column.key===state.selected&&!summary?'selected-column':''}"><button type="button" data-column="${column.key}" style="border:0;background:none;padding:0;color:inherit;font:inherit;display:flex;align-items:center;gap:5px">${!column.source?'↳':''} ${esc(column.label)}${column.required?' <span style="color:#cb8e67">*</span>':''}</button></th>`).join('')}</tr></thead><tbody>${rows.map((row,index)=>`<tr><td>${index+1}</td>${columns.map(column=>{
      let value=esc(row[column.key] || '');
      if (!column.source && editable) {
        value=column.type==='select'?`<select class="mm-inline-select" data-answer="${column.key}" data-row="${row.id}" aria-label="${esc(column.label)} dòng ${index+1}" ${state.closed?'disabled':''}><option value="">Chọn kết quả</option>${selectOptions((column.options||[]).map(option=>[option,option]),row[column.key])}</select>`:`<input type="${column.type==='number'?'number':column.type==='date'?'date':'text'}" data-answer="${column.key}" data-row="${row.id}" value="${esc(row[column.key]||'')}" aria-label="${esc(column.label)} dòng ${index+1}" ${state.closed?'disabled':''}>`;
      } else if (!column.source && column.type==='select') value=row[column.key]?pill(row[column.key],row[column.key]==='Cần bổ sung'?'amber':''): '<span style="color:#b3c0b7">Chưa phản hồi</span>';
      else if (!column.source && !value) value='<span style="color:#b3c0b7">—</span>';
      return `<td class="${!column.source?'response-column':''} ${column.key===state.selected&&!summary?'selected-column':''}">${value}</td>`;
    }).join('')}</tr>`).join('') || `<tr><td colspan="${columns.length+1}" class="mm-empty">Không có dòng phù hợp.</td></tr>`}</tbody></table></div>`;
  }
  function configuration() {
    return sectionHead('Cấu hình chiến dịch','Thiết lập thông tin, thời hạn và hướng dẫn trước khi phân phối dữ liệu.')+`<div class="mm-two-panels"><section class="mm-card"><div class="mm-card-head"><h3>Thông tin chiến dịch</h3>${pill('Bản nháp','gray')}</div><div class="mm-card-body mm-fields">${field('Tên chiến dịch',formInput('name',state.name),true)}${field('Mã chiến dịch',`<input class="mm-input" value="${creating?'Tự sinh khi tạo':'MM-202610-001'}" readonly>`)}${field('Hạn cuối PGD phản hồi','<div data-deadline-target></div>')}${field('Mẫu email','<select class="mm-select"><option>Mail Merge · Yêu cầu đối soát hồ sơ</option><option>Mail Merge · Thu thập thông tin PGD</option></select>',true)}${field('Tiêu đề email',formInput('subject',state.subject),true)}${field('Hướng dẫn dành cho PGD',`<textarea class="mm-textarea" data-config="instructions">${esc(state.instructions)}</textarea>`,true)}</div></section><aside class="mm-card"><div class="mm-card-head"><h3>Chiến dịch này hoạt động như thế nào?</h3></div><div class="mm-card-body"><ul class="mm-checklist"><li><span class="mm-check">1</span><div>Tải một bảng Excel<p>Mỗi dòng là một hồ sơ hoặc nội dung cần xác nhận.</p></div></li><li><span class="mm-check">2</span><div>Thiết kế cột PGD phản hồi<p>Giữ cột nguồn chỉ đọc, thêm droplist và trường nhập.</p></div></li><li><span class="mm-check">3</span><div>Mỗi PGD nhận một link riêng<p>PGD chỉ xem các dòng và cột được phân phối.</p></div></li><li><span class="mm-check">4</span><div>Chốt một bộ kết quả cuối cùng<p>Giữ dữ liệu gốc, phản hồi và tiến độ đối soát.</p></div></li></ul><div class="mm-note">${icon('lock')}<span>Loại chiến dịch <strong>Mail Merge</strong> có tiến trình riêng, không dùng các bước duyệt lỗi và QLKV xác nhận của Book lỗi.</span></div></div></aside></div>`;
  }
  function upload() {
    return sectionHead('Tải dữ liệu','Chọn file nguồn và xác định vùng dữ liệu cần phân phối.',pill('Dữ liệu minh họa','gray'))+`<div class="mm-two-panels"><section class="mm-card"><div class="mm-card-head"><h3>File dữ liệu nguồn</h3>${pill('Phiên bản 01')}</div><div class="mm-card-body"><div class="mm-upload"><span class="mm-file-icon">XLSX</span><strong>Kéo thả file Excel vào đây</strong><span class="mm-hint">hoặc chọn tệp từ máy tính của anh</span><label class="ui-btn ui-btn-secondary">Chọn file<input type="file" accept=".xlsx,.xls,.csv" data-file-input hidden></label></div><div class="mm-file-row"><span class="mm-file-icon">XLSX</span><div><strong>${esc(state.file)}</strong><p>6 dòng mẫu · 6 cột nguồn · 3 PGD</p></div><span style="margin-left:auto">${pill('Sẵn sàng')}</span></div><div class="mm-note amber">Thông tin tệp có thể chọn thử. Bảng bên dưới vẫn dùng dữ liệu mẫu để anh duyệt thiết kế.</div><div class="mm-fields" style="margin-top:18px">${field('Sheet dữ liệu','<select class="mm-select"><option>Data_PGD</option><option>Danh_muc</option></select>')}${field('Dòng tiêu đề','<input type="number" min="1" value="1" class="mm-input">')}</div></div></section><aside class="mm-card"><div class="mm-card-head"><h3>Kiểm tra dữ liệu</h3></div><div class="mm-card-body"><ul class="mm-checklist"><li><span class="mm-check">✓</span><div>Nhận diện được dòng tiêu đề<p>Tên cột không trùng và không để trống.</p></div></li><li><span class="mm-check">✓</span><div>6 dòng có dữ liệu trong mẫu<p>Mỗi dòng được giữ một ID riêng để đối soát.</p></div></li><li><span class="mm-check">✓</span><div>Có cột mã PGD và email<p>Kiểm tra người nhận tại bước Mapping PGD / email.</p></div></li></ul></div></aside></div><section class="mm-card" style="margin-top:14px"><div class="mm-card-head"><h3>Xem trước dữ liệu nguồn</h3><span class="mm-hint">Không bao gồm cột phản hồi</span></div>${table(state.rows,aliveColumns().filter(column=>column.source),false,true)}</section>`;
  }
  function columnList(source) {
    return state.columns.filter(column=>column.source===source&&!column.removed).map(column=>`<div class="mm-column-row ${column.key===state.selected?'is-selected':''} ${!column.visible?'is-hidden':''}" data-column-row><span class="mm-column-drag" aria-hidden="true">⠿</span><span class="mm-field-symbol ${source?'':'green'}">${source?'T':column.type==='select'?'⌄':'↳'}</span><button class="mm-column-name" data-column="${column.key}" title="${esc(column.label)}">${esc(column.label)}</button><button type="button" class="ui-btn ui-btn-ghost ui-btn-icon ui-btn-sm" data-action="toggle-column" data-key="${column.key}" aria-label="${column.visible?'Ẩn':'Hiện'} ${esc(column.label)} với PGD" title="${column.visible?'Đang hiện với PGD':'Đang ẩn với PGD'}">${icon(column.visible?'eye':'hidden')}</button></div>`).join('');
  }
  function designer() {
    const selected=state.columns.find(column=>column.key===state.selected&&!column.removed)||aliveColumns()[0];
    state.selected=selected.key;
    const shown=aliveColumns().filter(column=>state.gridView==='team'||column.visible);
    const inspector=`<aside class="mm-card mm-inspector"><div class="mm-card-head"><h3>Thiết lập cột</h3><span class="mm-field-symbol green">${selected.source?'T':'⌄'}</span></div><div class="mm-inspector-section"><label class="mm-form-label" for="mm-column-name">TÊN HIỂN THỊ</label><input id="mm-column-name" class="mm-input" value="${esc(selected.label)}"><label class="mm-form-label" for="mm-column-type" style="margin-top:14px">KIỂU DỮ LIỆU</label><select id="mm-column-type" class="mm-select" ${selected.source?'disabled':''}>${selectOptions(typeOptions,selected.type)}</select><div class="mm-toggle-row"><span>Hiển thị với PGD</span>${toggle('visible',selected.visible)}</div><div class="mm-toggle-row"><span>PGD bắt buộc điền</span>${toggle('required',selected.required,!selected.source?false:true)}</div><div class="mm-hint">${selected.source?'Cột dữ liệu nguồn chỉ đọc. PGD không sửa giá trị gốc.':'Cột phản hồi do PGD nhập khi mở link.'}</div></div><div class="mm-inspector-section">${selected.type==='select'?`<label class="mm-form-label" for="mm-column-options">DANH SÁCH LỰA CHỌN</label><select class="mm-select" id="mm-options-source"><option>Team nhập danh sách</option><option>Từ sheet Danh_muc (xem thử)</option><option>Từ Master Data (xem thử)</option></select><textarea id="mm-column-options" class="mm-textarea" style="margin-top:9px">${esc((selected.options||[]).join('\n'))}</textarea><div class="mm-hint">Mỗi dòng là một lựa chọn.</div><div class="mm-options">${(selected.options||[]).map(option=>`<span class="mm-option">${esc(option)}</span>`).join('')}</div>`:`<span class="mm-form-label">VỊ TRÍ TRONG BẢNG</span><div class="mm-inline-actions">${button('move-up','← Sang trái')}${button('move-down','Sang phải →')}</div><p class="mm-hint">Thứ tự cột sẽ được giữ khi PGD mở link và khi xuất báo cáo.</p>`}</div><div class="mm-inspector-footer">${button('delete-column','Xóa cột')}${button('apply-column','Áp dụng',true)}</div></aside>`;
    return sectionHead('Thiết kế bảng phản hồi','Chọn cột để đổi tên, ẩn với PGD hoặc cấu hình nội dung được phép điền.',`${pill(`${aliveColumns().length} cột`)}${button('add-column',`${icon('plus')} Thêm cột phản hồi`)}`)+`<div class="mm-designer"><aside class="mm-card"><div class="mm-card-head"><h3>Các cột dữ liệu</h3><span class="mm-count">${aliveColumns().length}</span></div><label class="mm-search">${icon('search')}<input data-column-search placeholder="Tìm cột dữ liệu" aria-label="Tìm cột dữ liệu"></label><div class="mm-list-label">DỮ LIỆU NGUỒN <span>${aliveColumns().filter(column=>column.source).length}</span></div><div class="mm-column-list">${columnList(true)}</div><div class="mm-list-label">PGD PHẢN HỒI <span>${responseColumns().length}</span></div><div class="mm-column-list">${columnList(false)}</div><button class="ui-btn ui-btn-secondary mm-add-column" data-action="add-column">+ Thêm cột phản hồi</button><div class="mm-source-note">${icon('lock')} Giá trị nguồn luôn được giữ nguyên</div></aside><section class="mm-card"><div class="mm-card-head"><div><h3>${icon('grid')} Bảng dữ liệu làm việc</h3><p>${esc(state.file)}</p></div>${pill('6 dòng mẫu','gray')}</div><div class="mm-table-toolbar"><div class="mm-tabs-small"><button data-grid-view="team" class="${state.gridView==='team'?'is-active':''}">Team</button><button data-grid-view="pgd" class="${state.gridView==='pgd'?'is-active':''}">PGD nhìn thấy</button></div><div><select data-shop-filter aria-label="Lọc PGD"><option value="all">Tất cả PGD</option>${selectOptions(state.shops.map(shop=>[shop.code,shop.name]),state.shopFilter)}</select></div></div>${table(shopRows(state.shopFilter),shown)}<div class="mm-table-footer"><span>${shopRows(state.shopFilter).length} dòng · ${shown.length} cột hiển thị</span><span class="mm-page-indicator">1</span></div></section>${inspector}</div><div class="mm-note">${icon('eye')}<span><strong>Thiết kế một lần, phân phối theo từng PGD.</strong> Cột màu xanh là cột phản hồi. Dùng “PGD nhìn thấy” hoặc “Xem giao diện PGD” để kiểm tra các cột đã ẩn.</span></div>`;
  }
  function mapping() {
    const match=state.mapping.shop==='shop_code'&&aliveColumns().some(column=>column.key==='shop_code');
    return sectionHead('Mapping PGD / email','Xác định cột phân nhóm dữ liệu và người nhận trước khi phát hành.',pill(match?'3 / 3 PGD đã khớp':'Cần kiểm tra mapping',match?'':'amber'))+`<div class="mm-two-panels"><section class="mm-card"><div class="mm-card-head"><h3>Quy tắc phân phối</h3>${pill('Một link / PGD','gray')}</div><div class="mm-card-body mm-fields">${field('Cột xác định phòng giao dịch',`<select class="mm-select" data-mapping="shop">${selectOptions(aliveColumns().filter(column=>column.source).map(column=>[column.key,column.label]),state.mapping.shop)}</select>`)}${field('Nguồn email người nhận',`<select class="mm-select" data-mapping="email">${selectOptions([['master','Email PGD từ Master Data'],['email','Cột Email PGD trong file']],state.mapping.email)}</select>`)}<div class="wide mm-note">${icon('lock')}<span>Mỗi PGD nhận toàn bộ dòng có cùng mã PGD. Link chỉ mở dữ liệu được phân cho PGD đó.</span></div></div></section><aside class="mm-card"><div class="mm-card-head"><h3>Kết quả kiểm tra mapping</h3></div><div class="mm-card-body"><div class="mm-toggle-row"><span>PGD hợp lệ</span><strong>${match?'3':'0'} / 3</strong></div><div class="mm-toggle-row"><span>Dòng được phân phối</span><strong>${match?'6':'0'} / 6</strong></div><div class="mm-toggle-row"><span>Email hợp lệ trong mẫu</span><strong>3 / 3</strong></div>${!match?'<div class="mm-note amber">Cột đã chọn không chứa mã PGD. Chọn “Mã PGD” để xem mapping phù hợp.</div>':''}</div></aside></div><section class="mm-card" style="margin-top:14px"><div class="mm-card-head"><h3>Danh sách người nhận</h3><span class="mm-hint">Email mẫu dùng miền example.com</span></div><div class="mm-grid-scroll" style="min-height:0"><table class="mm-table"><thead><tr><th>STT</th><th>Mã PGD</th><th>Phòng giao dịch</th><th>Email nhận</th><th>Số dòng</th><th>Kết quả mapping</th></tr></thead><tbody>${state.shops.map((shop,index)=>`<tr><td>${index+1}</td><td>${shop.code}</td><td>${shop.name}</td><td>${shop.email}</td><td>2</td><td>${pill(match?'Đã khớp':'Chưa khớp',match?'':'amber')}</td></tr>`).join('')}</tbody></table></div></section>`;
  }
  function delivery() {
    const submitted=state.shops.filter(shop=>shop.status==='submitted').length;
    return sectionHead('Phát hành & theo dõi','Kiểm tra email, tạo link riêng và theo dõi tiến độ phản hồi.',`${button('email-preview','Xem email mẫu')}${button('send-preview','Gửi mô phỏng',true)}`)+`<div class="mm-stats">${stat('PGD nhận dữ liệu','3','6 dòng được phân phối')}${stat('Email đã gửi (mẫu)',state.shops.filter(shop=>shop.delivery==='sent').length,'Trạng thái mô phỏng')}${stat('PGD đã gửi phản hồi',submitted,`${Math.round(submitted/3*100)}% hoàn thành`)}${stat('Hạn cuối phản hồi','24/10','17:00 · 2026')}</div><section class="mm-card"><div class="mm-card-head"><h3>Theo dõi link PGD</h3>${pill(state.closed?'Đã khóa phản hồi':'Đang thu thập',state.closed?'gray':'')}</div><table class="mm-table"><thead><tr><th>STT</th><th>Phòng giao dịch</th><th>Email</th><th>Gửi email</th><th>Phản hồi</th><th>Link</th><th>Thao tác</th></tr></thead><tbody>${state.shops.map((shop,index)=>`<tr><td>${index+1}</td><td><strong>${shop.code}</strong><br><span class="mm-hint">${shop.name}</span></td><td>${shop.email}</td><td>${pill(shop.delivery==='sent'?'Đã gửi (mẫu)':'Chưa gửi',shop.delivery==='sent'?'':'gray')}</td><td>${pill(shop.status==='submitted'?'Đã gửi phản hồi':shop.status==='editing'?'Đang nhập':'Chưa mở',shop.status==='submitted'?'':shop.status==='editing'?'blue':'gray')}</td><td>${pill(shop.revoked?'Đã thu hồi':state.closed?'Đã khóa':'Đang hiệu lực',shop.revoked?'red':state.closed?'gray':'')}</td><td><div class="mm-inline-actions">${button('shop-preview','Xem link',false,`data-shop="${shop.code}"`)}${button('revoke-link',shop.revoked?'Cấp lại':'Thu hồi',false,`data-shop="${shop.code}"`)}</div></td></tr>`).join('')}</tbody></table></section><div class="mm-note">${icon('lock')}<span>Thu hồi link ngừng quyền truy cập. Phản hồi PGD đã gửi vẫn được giữ trong kết quả chiến dịch.</span></div>`;
  }
  function report() {
    const answered=state.rows.filter(row=>row.response).length;
    return sectionHead('Chốt & xuất báo cáo','Tổng hợp dữ liệu nguồn cùng phản hồi PGD tại thời điểm chốt.',`${button('export-report',`${icon('download')} Xuất CSV mẫu`)}${button('close-campaign',state.closed?'Đã chốt kết quả':'Chốt kết quả mẫu',true,state.closed?'disabled':'')}`)+`<div class="mm-stats">${stat('Tổng số dòng',state.rows.length,'Giữ đầy đủ dữ liệu gốc')}${stat('Đã có phản hồi',answered,`${Math.round(answered/6*100)}% dữ liệu mẫu`)}${stat('Chưa phản hồi',6-answered,'Vẫn xuất hiện trong báo cáo')}${stat('Trạng thái',state.closed?'Đã chốt':'Bản nháp',state.closed?'PGD không thể sửa phản hồi':'Có thể xem thử và điều chỉnh')}</div><section class="mm-card"><div class="mm-card-head"><h3>Kết quả tổng hợp</h3>${pill(state.closed?'Snapshot mẫu · Phiên bản 01':'Dữ liệu mẫu hiện tại','gray')}</div>${table(state.rows,aliveColumns(),false,true)}</section><div class="mm-note">${icon('lock')}<span>Khi chốt, bảng kết quả giữ cả các dòng chưa có phản hồi và thông tin PGD. CSV tải xuống là dữ liệu minh họa đang hiển thị trong bản xem thử.</span></div>`;
  }
  const renderers=[configuration,upload,designer,mapping,delivery,report];
  function render() {
    state.step=Math.max(1,Math.min(6,state.step));
    root.querySelector('[data-campaign-title]').textContent=state.name||'Chiến dịch Mail Merge mới';
    root.querySelectorAll('[data-step]').forEach(button=>{
      const number=Number(button.dataset.step);button.classList.toggle('is-current',number===state.step);button.classList.toggle('is-done',number<state.step);
      if(number===state.step)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');
      button.querySelector('.mm-step-number').textContent=number<state.step?'✓':number;
    });
    content.querySelectorAll('[data-datetime-date]').forEach(input=>input._flatpickr?.destroy());
    content.innerHTML=renderers[state.step-1]();
    const deadlineTarget=content.querySelector('[data-deadline-target]');
    if(deadlineTarget){
      deadlineTarget.append(root.querySelector('[data-deadline-template]').content.cloneNode(true));
      const source=deadlineTarget.querySelector('[data-datetime-source] input');
      source.value=state.deadline;source.dataset.config='deadline';
      window.campaignDateTimePicker?.initAll(deadlineTarget);
    }
    root.querySelector('[data-action=previous]').disabled=state.step===1;
    root.querySelector('[data-action=next]').disabled=state.step===6;
    root.querySelector('[data-next-step]').textContent=state.step<6?`bước ${state.step+1}`:'';
  }
  function modal(title,html,eyebrow='MAIL MERGE · BẢN XEM THỬ') {
    root.querySelector('#mm-dialog-title').textContent=title;
    root.querySelector('[data-dialog-eyebrow]').textContent=eyebrow;
    root.querySelector('[data-dialog-content]').innerHTML=html;
    if(!dialog.open)dialog.showModal();
  }
  function pgdPreview() {
    const shop=state.shops.find(item=>item.code===selectedShop)||state.shops[0];selectedShop=shop.code;
    modal(state.name,`<div class="mm-section-head"><div>${pill(shop.code)} <span>${shop.name}</span><p style="margin-top:8px">${esc(state.instructions)}</p></div><label class="mm-form-label">Xem với PGD<select class="mm-select" data-preview-shop>${selectOptions(state.shops.map(item=>[item.code,item.name]),selectedShop)}</select></label></div>${shop.revoked?'<div class="mm-note amber">Link mẫu đã thu hồi. PGD này không thể xem hoặc chỉnh sửa dữ liệu.</div>':`${table(shopRows(shop.code),aliveColumns().filter(column=>column.visible),!state.closed,true)}<div style="display:flex;align-items:center;justify-content:space-between;margin-top:16px"><span class="mm-hint">${state.closed?'Chiến dịch mẫu đã chốt. Phản hồi chỉ đọc.':'Các cột dữ liệu nguồn chỉ đọc. Anh có thể điền thử các cột phản hồi.'}</span>${button('submit-preview','Gửi phản hồi mẫu',true,state.closed?'disabled':'')}</div>`}`,'GIAO DIỆN PGD · DỮ LIỆU MẪU');
  }
  function exportReport() {
    const columns=aliveColumns();
    const csvCell=value=>'"'+String(value??'').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';
    const lines=[columns.map(column=>column.label),...state.rows.map(row=>columns.map(column=>row[column.key]||''))];
    const url=URL.createObjectURL(new Blob(['\ufeff'+lines.map(line=>line.map(csvCell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download='Mail_Merge_Ket_qua_mau_202610.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('Đã tải báo cáo CSV từ dữ liệu mẫu.');
  }
  root.addEventListener('click',event=>{
    const step=event.target.closest('[data-step]');if(step){state.step=Number(step.dataset.step);render();return;}
    const column=event.target.closest('[data-column]');if(column){state.selected=column.dataset.column;if(state.step===3&&!dialog.contains(column))render();return;}
    const view=event.target.closest('[data-grid-view]');if(view){state.gridView=view.dataset.gridView;render();return;}
    const action=event.target.closest('[data-action]');if(!action)return;
    const selected=state.columns.find(column=>column.key===state.selected);
    switch(action.dataset.action){
      case 'previous':state.step--;render();break;
      case 'next':state.step++;render();break;
      case 'pgd-preview':pgdPreview();break;
      case 'close-dialog':dialog.close();break;
      case 'shop-preview':selectedShop=action.dataset.shop;pgdPreview();break;
      case 'toggle-column':{const target=state.columns.find(column=>column.key===action.dataset.key);target.visible=!target.visible;render();break;}
      case 'save-draft':if(!state.name.trim()){state.step=1;render();toast('Vui lòng nhập tên chiến dịch.');break;}try{localStorage.setItem(storageKey,JSON.stringify(state));root.querySelector('[data-campaign-title]').textContent=state.name||'Chiến dịch Mail Merge mới';toast('Đã lưu bản xem thử trên trình duyệt này.');}catch(_){toast('Trình duyệt không cho phép lưu bản xem thử.');}break;
      case 'apply-column':{
        const label=root.querySelector('#mm-column-name').value.trim();if(!label){toast('Vui lòng nhập tên cột.');break;}
        const type=root.querySelector('#mm-column-type').value;
        const options=root.querySelector('#mm-column-options')?.value.split('\n').map(value=>value.trim()).filter(Boolean)||selected.options||[];
        if(type==='select'&&!options.length){toast('Droplist cần ít nhất một lựa chọn.');break;}
        selected.label=label;selected.type=type;selected.options=[...new Set(options)];
        selected.visible=root.querySelector('[data-column-option=visible]').checked;
        selected.required=!selected.source&&root.querySelector('[data-column-option=required]').checked;
        render();toast('Đã cập nhật thiết kế cột trong bản xem thử.');break;
      }
      case 'move-up':case 'move-down':{const current=state.columns.indexOf(selected),next=current+(action.dataset.action==='move-up'?-1:1);if(next>=0&&next<state.columns.length){[state.columns[current],state.columns[next]]=[state.columns[next],state.columns[current]];render();}break;}
      case 'delete-column':if(aliveColumns().length<2){toast('Bảng cần ít nhất một cột.');break;}selected.removed=true;state.selected=aliveColumns()[0].key;render();toast('Đã bỏ cột khỏi bảng mẫu. File nguồn được giữ nguyên.');break;
      case 'add-column':modal('Thêm cột phản hồi',`<div class="mm-fields">${field('Tên cột','<input id="mm-new-label" class="mm-input" placeholder="Ví dụ: Lý do chưa hoàn tất">',true)}${field('Kiểu dữ liệu',`<select id="mm-new-type" class="mm-select">${selectOptions(typeOptions,'select')}</select>`,true)}${field('Lựa chọn cho droplist (mỗi dòng một mục)','<textarea id="mm-new-options" class="mm-textarea">Đồng ý\nKhông đồng ý\nCần kiểm tra thêm</textarea>',true)}</div><div style="display:flex;justify-content:flex-end;margin-top:18px">${button('confirm-add-column','Thêm cột',true)}</div>`);break;
      case 'confirm-add-column':{
        const label=root.querySelector('#mm-new-label').value.trim();if(!label){toast('Vui lòng nhập tên cột.');break;}
        const type=root.querySelector('#mm-new-type').value,options=root.querySelector('#mm-new-options').value.split('\n').map(value=>value.trim()).filter(Boolean);
        if(type==='select'&&!options.length){toast('Droplist cần ít nhất một lựa chọn.');break;}
        const key='answer_'+Date.now();state.columns.push({key,label,type,source:false,visible:true,required:false,options:[...new Set(options)]});state.selected=key;dialog.close();state.step=3;render();break;
      }
      case 'email-preview':modal('Email gửi phòng giao dịch',`<div class="mm-email-preview"><strong>Đến:</strong> ${state.shops[0].email}<br><strong>Tiêu đề:</strong> ${esc(state.subject.replace(/{{report_month}}/g,'10/2026').replace(/{{shop_name}}/g,state.shops[0].name))}<hr>Kính gửi PGD ${state.shops[0].name},<p>${esc(state.instructions)}</p><p>PGD có <strong>2 dòng</strong> cần kiểm tra trong kỳ tháng 10/2026.</p>${button('pgd-preview','Mở bảng đối soát mẫu',true)}<p>Hạn phản hồi: 17:00 ngày 24/10/2026.</p></div>`);break;
      case 'send-preview':modal('Gửi email mô phỏng',`<p>Thử trạng thái gửi cho 3 PGD trong dữ liệu mẫu. Không có email thật được gửi.</p><ul class="mm-checklist">${state.shops.map(shop=>`<li><span class="mm-check">✓</span><div>${shop.name}<p>${shop.email}</p></div></li>`).join('')}</ul><div style="display:flex;justify-content:flex-end;margin-top:16px">${button('confirm-send','Mô phỏng gửi cho 3 PGD',true)}</div>`);break;
      case 'confirm-send':state.shops.forEach(shop=>shop.delivery='sent');dialog.close();render();toast('Đã mô phỏng trạng thái gửi email cho 3 PGD.');break;
      case 'revoke-link':{const shop=state.shops.find(shop=>shop.code===action.dataset.shop);modal(shop.revoked?'Cấp lại link mẫu':'Thu hồi link mẫu',`<p>${esc(shop.name)} sẽ ${shop.revoked?'có thể mở lại':'không thể truy cập'} bảng dữ liệu mẫu. Phản hồi đã có được giữ nguyên.</p><div style="display:flex;justify-content:flex-end;margin-top:16px">${button('confirm-revoke',shop.revoked?'Cấp lại link mẫu':'Thu hồi link mẫu',true,`data-shop="${shop.code}"`)}</div>`);break;}
      case 'confirm-revoke':{const shop=state.shops.find(shop=>shop.code===action.dataset.shop);shop.revoked=!shop.revoked;dialog.close();render();toast('Đã cập nhật trạng thái link mẫu.');break;}
      case 'submit-preview':{
        const rows=shopRows(selectedShop),required=responseColumns().filter(column=>column.visible&&column.required);
        if(rows.some(row=>required.some(column=>!String(row[column.key]||'').trim()))){toast('Vui lòng điền đủ các cột phản hồi bắt buộc.');break;}
        state.shops.find(shop=>shop.code===selectedShop).status='submitted';dialog.close();render();toast('Đã ghi nhận phản hồi trong dữ liệu mẫu.');break;
      }
      case 'export-report':exportReport();break;
      case 'close-campaign':modal('Chốt kết quả mẫu',`<p>Bảng mẫu có ${state.rows.filter(row=>!row.response).length} dòng chưa phản hồi. Các dòng này vẫn được giữ trong báo cáo. Sau khi chốt, giao diện PGD chuyển sang chỉ đọc.</p><div style="display:flex;justify-content:flex-end;margin-top:16px">${button('confirm-close','Chốt kết quả mẫu',true)}</div>`);break;
      case 'confirm-close':state.closed=true;dialog.close();render();toast('Đã chốt bộ kết quả mẫu.');break;
    }
  });
  root.addEventListener('input',event=>{
    const target=event.target;
    if(target.matches('[data-config]'))state[target.dataset.config]=target.value;
    if(target.matches('[data-column-search]'))root.querySelectorAll('[data-column-row]').forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(target.value.toLowerCase()));
    if(target.matches('[data-answer]'))state.rows.find(row=>row.id===Number(target.dataset.row))[target.dataset.answer]=target.value;
  });
  root.addEventListener('dragover',event=>{if(event.target.closest('.mm-upload'))event.preventDefault();});
  root.addEventListener('drop',event=>{
    if(!event.target.closest('.mm-upload'))return;
    event.preventDefault();
    const file=event.dataTransfer?.files[0];
    if(file){state.file=file.name;render();toast('Đã chọn tên tệp để xem thử. Bảng hiện tại vẫn là dữ liệu mẫu.');}
  });
  root.addEventListener('change',event=>{
    const target=event.target;
    if(target.matches('[data-shop-filter]')){state.shopFilter=target.value;render();}
    if(target.matches('[data-preview-shop]')){selectedShop=target.value;pgdPreview();}
    if(target.matches('[data-mapping]')){state.mapping[target.dataset.mapping]=target.value;render();}
    if(target.matches('[data-answer]'))state.rows.find(row=>row.id===Number(target.dataset.row))[target.dataset.answer]=target.value;
    if(target.matches('[data-file-input]')&&target.files[0]){state.file=target.files[0].name;render();toast('Đã chọn tên tệp để xem thử. Bảng hiện tại vẫn là dữ liệu mẫu.');}
    if(target.id==='mm-column-type'){
      const selected=state.columns.find(column=>column.key===state.selected);
      selected.label=root.querySelector('#mm-column-name').value||selected.label;selected.type=target.value;
      if(selected.type==='select'&&!selected.options?.length)selected.options=['Đồng ý','Không đồng ý'];render();
    }
    if(target.id==='mm-options-source'){
      const choices=target.selectedIndex===1?['Đã đủ hồ sơ','Thiếu biên bản','Thiếu chữ ký']:target.selectedIndex===2?['Đồng ý','Không đồng ý','Cần kiểm tra thêm']:null;
      if(choices)root.querySelector('#mm-column-options').value=choices.join('\n');
    }
  });
  try { const saved=JSON.parse(localStorage.getItem(storageKey)||'null'); if(!creating&&saved?.columns?.length&&saved?.rows?.length&&saved?.shops?.length){state=saved;state.step=Number(new URLSearchParams(location.search).get('step'))||3;} }catch(_){/* Default sample remains available. */}
  render();
});
