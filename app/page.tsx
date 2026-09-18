'use client'

import { FormEvent, useMemo, useState } from 'react'
import { Bot, BriefcaseBusiness, ChevronDown, CircleUserRound, MessageCircleMore, Paperclip, Send, Sparkles, UsersRound } from 'lucide-react'

type Scope = 'Личное' | 'Семья' | 'Работа'
type Agent = { id:string; name:string; role:string; icon:string; model:string }
type Msg = { id:number; who:'user'|'assistant'; text:string; agent?:string }

const agents: Agent[] = [
  {id:'elir',name:'Элир',role:'Главный помощник и координатор',icon:'✦',model:'gpt-5.6-sol'},
  {id:'strategy',name:'Стратег',role:'Проекты, решения, развитие СКИФ',icon:'⌁',model:'gpt-5.6-terra'},
  {id:'sales',name:'Продажник',role:'Продажа земельных участков',icon:'◈',model:'gpt-5.6-terra'},
  {id:'finance',name:'Финансист',role:'Расчёты, бюджет, финансовые планы',icon:'₽',model:'gpt-5.6-terra'},
  {id:'law',name:'Юрист',role:'Документы и правовая логика',icon:'§',model:'gpt-5.6-terra'},
  {id:'content',name:'Контент',role:'Посты, объявления, презентации',icon:'✎',model:'gpt-5.6-luna'},
  {id:'tech',name:'Технарь',role:'Приложение, сервер, GitHub, автоматизация',icon:'⌘',model:'gpt-5.6-terra'},
]

export default function Home(){
  const [scope,setScope]=useState<Scope>('Личное')
  const [agent,setAgent]=useState<Agent>(agents[0])
  const [openAgents,setOpenAgents]=useState(false)
  const [text,setText]=useState('')
  const [busy,setBusy]=useState(false)
  const [messages,setMessages]=useState<Msg[]>([
    {id:1,who:'assistant',agent:'Элир',text:'Я здесь. Это наше общее пространство: можем думать вдвоём или позвать специалистов на совет. С чего начнём?'}
  ])

  const placeholder = useMemo(()=> scope==='Работа' ? 'Напиши рабочую задачу…' : scope==='Семья' ? 'Напиши о семейной задаче…' : 'Напиши Элиру…',[scope])

  async function send(council=false){
    const value=text.trim(); if(!value || busy) return
    const next=[...messages,{id:Date.now(),who:'user' as const,text:value}]
    setMessages(next); setText(''); setBusy(true); setOpenAgents(false)
    try{
      const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:value,scope,agent:agent.id,council,history:next.slice(-12)})})
      const data=await r.json()
      setMessages(m=>[...m,{id:Date.now()+1,who:'assistant',agent:data.agent || agent.name,text:data.text || data.error || 'Не удалось получить ответ.'}])
    }catch{
      setMessages(m=>[...m,{id:Date.now()+1,who:'assistant',agent:'Элир',text:'Сервер пока не подключён. Интерфейс уже работает — осталось добавить OPENAI_API_KEY на сервере.'}])
    }finally{setBusy(false)}
  }

  function onSubmit(e:FormEvent){e.preventDefault(); send(false)}

  return <main className="shell">
    <header className="topbar">
      <div className="brand"><div className="orb">✦</div><div><strong>Элир</strong><span>онлайн · OpenAI</span></div></div>
      <button className="avatar"><CircleUserRound size={22}/></button>
    </header>

    <nav className="scope-tabs">
      {(['Личное','Семья','Работа'] as Scope[]).map(s=><button key={s} onClick={()=>setScope(s)} className={scope===s?'active':''}>{s==='Личное'?<MessageCircleMore/>:s==='Семья'?<UsersRound/>:<BriefcaseBusiness/>}{s}</button>)}
    </nav>

    <section className="agent-strip">
      <button className="agent-current" onClick={()=>setOpenAgents(v=>!v)}><span>{agent.icon}</span><div><b>{agent.name}</b><small>{agent.role}</small></div><ChevronDown size={18}/></button>
      {openAgents && <div className="agent-menu">{agents.map(a=><button key={a.id} onClick={()=>{setAgent(a);setOpenAgents(false)}}><span className="agent-icon">{a.icon}</span><div><b>{a.name}</b><small>{a.role}</small></div><em>{a.model.replace('gpt-5.6-','')}</em></button>)}</div>}
    </section>

    <section className="chat">
      <div className="day">Сегодня</div>
      {messages.map(m=><div key={m.id} className={`row ${m.who}`}>
        {m.who==='assistant' && <div className="mini-orb">✦</div>}
        <div className="bubble">{m.who==='assistant' && <small>{m.agent}</small>}<p>{m.text}</p></div>
      </div>)}
      {busy && <div className="row assistant"><div className="mini-orb">✦</div><div className="bubble typing"><i/><i/><i/></div></div>}
    </section>

    <section className="composer-wrap">
      <div className="quick-actions">
        <button onClick={()=>setOpenAgents(true)}><Bot size={16}/> Специалист</button>
        <button onClick={()=>send(true)} disabled={!text.trim()||busy}><Sparkles size={16}/> Созвать совет</button>
      </div>
      <form className="composer" onSubmit={onSubmit}>
        <button type="button" className="ghost"><Paperclip size={21}/></button>
        <textarea value={text} onChange={e=>setText(e.target.value)} placeholder={placeholder} rows={1} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(false)}}}/>
        <button className="send" disabled={!text.trim()||busy}><Send size={19}/></button>
      </form>
    </section>
  </main>
}