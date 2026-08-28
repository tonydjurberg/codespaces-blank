const conversations = [
  {name:'Marina Silva', initials:'MS', color:'coral', preview:'Perfeito! Pode separar tambem um brinquedo?', time:'10:45', unread:false, assigned:true},
  {name:'Rafael Mendes', initials:'RM', color:'mint', preview:'O kit inicial para filhotes ainda esta em promocao?', time:'10:39', unread:true, assigned:true},
  {name:'Ana Paula', initials:'AP', color:'yellow', preview:'Obrigada! Passo ai depois do trabalho.', time:'10:21', unread:true, assigned:false},
  {name:'Carlos Eduardo', initials:'CE', color:'lavender', preview:'Tem horario para banho e tosa amanha?', time:'09:58', unread:true, assigned:true},
  {name:'Beatriz Lima', initials:'BL', color:'peach', preview:'A Lola ficou linda depois do banho!', time:'Ontem', unread:false, assigned:true},
  {name:'Joao Victor', initials:'JV', color:'blue', preview:'Posso mudar o endereco da entrega?', time:'Ontem', unread:true, assigned:false}
];
const defaultAppointments = [
  {day:'SEG', date:'24', events:[['09:00','Lola','Banho e secagem','mint-event']]},
  {day:'TER', date:'25', events:[['11:30','Toby','Banho e tosa completo','']]},
  {day:'WED', date:'26', events:[]},
  {day:'QUI', date:'27', events:[['02:00','Bento','Corte de unhas','lav-event']]},
  {day:'SEX', date:'28', events:[['10:30','Luna','Banho e tosa completo',''],['03:00','Milo','Desembolo de pelos','mint-event']]},
  {day:'SAB', date:'29', events:[['09:30','Nina','Banho e secagem','lav-event']]},
  {day:'DOM', date:'30', events:[]}
];
const savedAppointments = JSON.parse(localStorage.getItem('vaniasAppointments') || '[]');
const appointments = [...defaultAppointments];
const savedMessages = JSON.parse(localStorage.getItem('vaniasMessages') || '[]');
let activeConversation = 'Marina Silva';
const customers = [{name:'Marina Silva',pet:'Luna e Nino',phone:'+55 11 99824-1042',tag:'VIP'},{name:'Rafael Mendes',pet:'Toby',phone:'+55 11 99712-4431',tag:'Frequente'},{name:'Ana Paula',pet:'Mel',phone:'+55 11 99621-8834',tag:'Novo'}];
const prices = [{name:'Banho e tosa completo',description:'Banho, secagem, tosa e perfume',price:'R$ 85,00'},{name:'Banho e secagem',description:'Para pets de pelo curto',price:'R$ 50,00'},{name:'Corte de unhas',description:'Corte seguro e cuidadoso',price:'R$ 20,00'},{name:'Desembolo de pelos',description:'Tratamento para pelos embaraçados',price:'R$ 65,00'}];
const $ = selector => document.querySelector(selector);
function persist(){localStorage.setItem('vaniasAppointments',JSON.stringify(savedAppointments));localStorage.setItem('vaniasMessages',JSON.stringify(savedMessages));}
function escapeHtml(value){return String(value).replace(/[&<>'"]/g,character=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character]));}
function renderConversations(list = conversations){
  $('#conversation-list').innerHTML = list.map((item,index)=>`<div class="conversation ${index===0?'selected':''}" data-name="${item.name}"><div class="customer-avatar ${item.color}">${item.initials}</div><div class="conversation-main"><div class="conversation-top"><strong>${item.name}${item.unread?'<span class="unread-dot"></span>':''}</strong><time>${item.time}</time></div><p>${item.preview}</p></div></div>`).join('');
  document.querySelectorAll('.conversation').forEach(row=>row.addEventListener('click',()=>selectConversation(row.dataset.name)));
}
function selectConversation(name){
  activeConversation=name;
  document.querySelectorAll('.conversation').forEach(row=>row.classList.toggle('selected',row.dataset.name===name));
  const item=conversations.find(entry=>entry.name===name); if(!item)return;
  $('#chat-name').innerHTML=`${item.name} <span class="verified"><i data-lucide="badge-check"></i></span>`; $('#profile-name').textContent=item.name; $('#chat-subtitle').textContent='Online · Last seen just now'; lucide.createIcons();
}
function renderCalendar(){
  const head='<div class="cal-head"></div>'+appointments.map(day=>`<div class="cal-head ${day.date==='28'?'today':''}"><span>${day.day}</span><strong>${day.date}</strong></div>`).join('');
  const times=['09:00 AM','10:30 AM','11:30 AM','02:00 PM','03:00 PM','04:30 PM'];
  const rows=times.map(time=>`<div class="time-label">${time}</div>`+appointments.map(day=>{const event=day.events.find(entry=>entry[0]===time.slice(0,5).replace(':30',':30').replace(' AM','').replace(' PM',''));return `<div class="cal-slot">${event?`<div class="calendar-event ${event[3]}"><strong>${event[1]}</strong><span>${event[2]}</span></div>`:''}</div>`}).join('')).join('');
  $('#calendar-grid').innerHTML=head+rows;
}
function renderUpcoming(){
  const cards=[['Luna','Marina Silva','Today · 10:30 AM','Full grooming','🐕','coral'],['Bento','Camila Rocha','Today · 02:00 PM','Nail trim','🐶','lavender'],['Nina','Pedro Alves','Sat · 09:30 AM','Bath & blow dry','🐕','mint'],...savedAppointments.map(item=>[item.pet,item.owner,`${item.date} · ${item.time}`,item.service,'🐕','coral'])];
  $('#appointment-cards').innerHTML=cards.map(card=>`<div class="appointment-card"><div class="pet-icon ${card[5]}">${card[4]}</div><div><strong>${card[0]} <span>· ${card[1]}</span></strong><span>${card[3]}</span></div><span class="appointment-time">${card[2]}</span></div>`).join('');
}
function showToast(message){$('#toast span').textContent=message;$('#toast').classList.add('show');setTimeout(()=>$('#toast').classList.remove('show'),2400)}
function setView(view){const schedule=view==='schedule';$('#inbox-view').style.display=schedule?'none':'';$('#schedule').classList.toggle('visible',schedule);document.querySelectorAll('.nav-item').forEach(item=>item.classList.toggle('active',item.getAttribute('href')==='#'+view));}
renderConversations();renderCalendar();renderUpcoming();lucide.createIcons();
$('#conversation-search').addEventListener('input',event=>{const query=event.target.value.toLowerCase();renderConversations(conversations.filter(item=>`${item.name} ${item.preview}`.toLowerCase().includes(query)))});
document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(item=>item.classList.remove('active'));tab.classList.add('active');const filter=tab.dataset.filter;renderConversations(filter==='unread'?conversations.filter(item=>item.unread):filter==='assigned'?conversations.filter(item=>item.assigned):conversations)}));
document.querySelectorAll('.nav-item').forEach(item=>item.addEventListener('click',event=>{const href=item.getAttribute('href');if(href==='#schedule'){event.preventDefault();setView('schedule')}else if(href==='#inbox'){event.preventDefault();setView('inbox')}}));
const modal=$('#appointment-modal');
$('#new-appointment').addEventListener('click',()=>{modal.classList.add('open');modal.setAttribute('aria-hidden','false')});
$('#close-modal').addEventListener('click',()=>{modal.classList.remove('open');modal.setAttribute('aria-hidden','true')});
modal.addEventListener('click',event=>{if(event.target===modal){modal.classList.remove('open');modal.setAttribute('aria-hidden','true')}});
$('#appointment-form').addEventListener('submit',event=>{event.preventDefault();const data=new FormData(event.target);const booking={owner:data.get('owner'),pet:data.get('pet'),date:data.get('date'),time:data.get('time'),service:data.get('service'),notes:data.get('notes')};savedAppointments.push(booking);const selectedDay=appointments.find(day=>day.date===new Date(`${booking.date}T12:00:00`).getDate().toString().padStart(2,'0'));if(selectedDay)selectedDay.events.push([booking.time.slice(0,5),booking.pet,booking.service,'mint-event']);persist();renderCalendar();renderUpcoming();modal.classList.remove('open');modal.setAttribute('aria-hidden','true');showToast(`Appointment booked for ${booking.pet}`);event.target.reset()});
function restoreMessages(){savedMessages.filter(item=>item.conversation===activeConversation).forEach(item=>appendMessage(item.text,item.time,false));}
function appendMessage(text,time='Now',scroll=true){const message=document.createElement('div');message.className='message sent';message.innerHTML=`<p>${escapeHtml(text)}</p><time>${time} <i data-lucide="check-check"></i></time>`;$('#chat-body').appendChild(message);lucide.createIcons();if(scroll)$('#chat-body').scrollTop=$('#chat-body').scrollHeight;}
$('#send-message').addEventListener('click',()=>{const input=$('#message-input');const text=input.value.trim();if(!text)return;appendMessage(text);savedMessages.push({conversation:activeConversation,text,time:'Now'});persist();input.value='';showToast('Message sent')});
$('#message-input').addEventListener('keydown',event=>{if(event.key==='Enter')$('#send-message').click()});
document.querySelectorAll('.quick-replies button').forEach(button=>button.addEventListener('click',()=>{$('#message-input').value=button.textContent.replace('↵','').trim();$('#message-input').focus()}));
savedAppointments.forEach(item=>{const day=appointments.find(entry=>entry.date===new Date(`${item.date}T12:00:00`).getDate().toString().padStart(2,'0'));if(day)day.events.push([item.time.slice(0,5),item.pet,item.service,'mint-event'])});
renderCalendar();
restoreMessages();
function renderCustomers(list=customers){$('#customer-list').innerHTML=list.map(item=>`<div class="customer-row"><div class="customer-avatar coral">${item.name.split(' ').map(part=>part[0]).slice(0,2).join('')}</div><div><strong>${item.name}</strong><span>${item.pet} · ${item.phone}</span></div><span class="tag">${item.tag}</span><button class="icon-button" aria-label="Ligar"><i data-lucide="phone"></i></button></div>`).join('');lucide.createIcons()}
function renderPrices(){ $('#price-list').innerHTML=prices.map(item=>`<div class="price-card"><div class="stat-icon peach"><i data-lucide="scissors"></i></div><h3>${item.name}</h3><p>${item.description}</p><strong>${item.price}</strong></div>`).join('');lucide.createIcons() }
renderCustomers();renderPrices();
document.querySelectorAll('.nav-item').forEach(item=>item.addEventListener('click',event=>{const href=item.getAttribute('href');if(['#contacts','#broadcasts','#orders'].includes(href)){event.preventDefault();document.querySelectorAll('.management-view').forEach(view=>view.classList.remove('visible'));$('#inbox-view').style.display='none';$('#schedule').classList.remove('visible');const target=href==='#contacts'?'contacts-view':href==='#orders'?'orders-view':'broadcasts-view';$('#'+target).classList.add('visible');document.querySelectorAll('.nav-item').forEach(link=>link.classList.toggle('active',link===item))}}));
$('#customer-search').addEventListener('input',event=>renderCustomers(customers.filter(item=>`${item.name} ${item.pet}`.toLowerCase().includes(event.target.value.toLowerCase()))));
$('#call-customer').addEventListener('click',()=>window.location.href='tel:+5511998241042');
$('#broadcast-form').addEventListener('submit',event=>{event.preventDefault();showToast('Mensagem pronta para envio')});
$('#add-customer').addEventListener('click',()=>{const name=prompt('Nome do tutor:');if(!name)return;const pet=prompt('Nome do pet:')||'Pet';const phone=prompt('Telefone com DDD:')||'';customers.unshift({name,pet,phone,tag:'Novo'});renderCustomers();showToast('Cliente cadastrado')});
$('#add-price').addEventListener('click',()=>{const name=prompt('Nome do servico:');if(!name)return;const price=prompt('Preco (ex.: R$ 40,00):')||'R$ 0,00';prices.push({name,description:'Servico da Vania\'s Petshop',price});renderPrices();showToast('Servico adicionado')});
