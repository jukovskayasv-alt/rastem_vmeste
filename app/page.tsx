'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Bot, BriefcaseBusiness, ChevronDown, MessageCircleMore, Paperclip, Send, Sparkles, X } from 'lucide-react'

type Scope = 'Личное' | 'Работа'
type Agent = { id:string; name:string; role:string; icon:string; model:string }
type Msg = { id:number; who:'user'|'assistant'; text:string; agent?:string }

const agents: Agent[] = [
  {id:'elir',name:'Элир',role:'Главный помощник и координатор',icon:'✦',model:'GigaChat-3-Ultra'},
  {id:'strategy',name:'Стратег',role:'Проекты, решения, развитие СКИФ',icon:'⌁',model:'GigaChat-2-Pro'},
  {id:'sales',name:'Продажник',role:'Продажа земельных участков',icon:'◈',model:'GigaChat-2'},
  {id:'finance',name:'Финансист',role:'Расчёты, бюджет, финансовые планы',icon:'₽',model:'GigaChat-2-Pro'},
  {id:'law',name:'Юрист',role:'Документы и правовая логика',icon:'§',model:'GigaChat-2-Pro'},
  {id:'content',name:'Контент',role:'Посты, объявления, презентации',icon:'✎',model:'GigaChat-2'},
  {id:'tech',name:'Технарь',role:'Приложение, сервер, GitHub, автоматизация',icon:'⌘',model:'GigaChat-2-Pro'},
]
const welcome:Msg={id:1,who:'assistant',agent:'Элир',text:'Я здесь. Это твоё личное пространство: можем думать вдвоём или позвать специалистов на совет. С чего начнём?'}

export default function Home(){
  const [scope,setScope]=useState<Scope>('Личное')
  const [agent,setAgent]=useState<Agent>(agents[0])
  const [openAgents,setOpenAgents]=useState(false)
  const [openMemory,setOpenMemory]=useState(false)
  const [text,setText]=useState('')
  const [memory,setMemory]=useState('')
  const [busy,setBusy]=useState(false)
  const [ready,setReady]=useState(false)
  const [messages,setMessages]=useState<Msg[]>([welcome])

  const storageKey=`elir:svetlana:${scope}`

  useEffect(()=>{ setReady(true) },[])

  useEffect(()=>{
    if(!ready) return
    const raw=localStorage.getItem(storageKey)
    if(raw){
      try{
        const parsed=JSON.parse(raw)
        setMessages(parsed.messages?.length?parsed.messages:[welcome])
        setMemory(parsed.memory||'')
      }catch{setMessages([welcome]);setMemory('')}
    }else{setMessages([welcome]);setMemory('')}
  },[storageKey,ready])

  useEffect(()=>{
    if(!ready) return
    localStorage.setItem(storageKey,JSON.stringify({messages:messages.slice(-80),memory,updatedAt:new Date().toISOString()}))
  },[messages,memory,storageKey,ready])

  const placeholder = useMemo(()=> scope==='Работа' ? 'Напиши рабочую задачу…' : 'Напиши Элиру…',[scope])

  async function send(council=false){
    const value=text.trim(); if(!value || busy) return
    const next=[...messages,{id:Date.now(),who:'user' as const,text:value}]
    setMessages(next); setText(''); setBusy(true); setOpenAgents(false)
    try{
      const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        message:value,scope,agent:agent.id,council,profile:{id:'svetlana',name:'Светлана'},memory,history:next.slice(-12)
      })})
      const data=await r.json()
      setMessages(m=>[...m,{id:Date.now()+1,who:'assistant',agent:data.agent || agent.name,text:data.text || data.error || 'Не удалось получить ответ.'}])
    }catch{
      setMessages(m=>[...m,{id:Date.now()+1,who:'assistant',agent:'Элир',text:'Сервер пока не подключён. Интерфейс и локальная память уже работают.'}])
    }finally{setBusy(false)}
  }

  function onSubmit(e:FormEvent){e.preventDefault(); send(false)}

  return <main className="shell">
    <header className="topbar">
      <div className="brand"><div className="orb">✦</div><div><strong>Элир</strong><span>Светлана · GigaChat</span></div></div>
    </header>

    <nav className="scope-tabs">
      {(['Личное','Работа'] as Scope[]).map(s=><button key={s} onClick={()=>setScope(s)} className={scope===s?'active':''}>{s==='Личное'?<MessageCircleMore/>:<BriefcaseBusiness/>}{s}</button>)}
    </nav>

    <section className="agent-strip">
      <button className="agent-current" onClick={()=>setOpenAgents(v=>!v)}><span>{agent.icon}</span><div><b>{agent.name}</b><small>{agent.role}</small></div><ChevronDown size={18}/></button>
      {openAgents && <div className="agent-menu">{agents.map(a=><button key={a.id} onClick={()=>{setAgent(a);setOpenAgents(false)}}><span className="agent-icon">{a.icon}</span><div><b>{a.name}</b><small>{a.role}</small></div><em>{a.model.replace('GigaChat-','')}</em></button>)}</div>}
    </section>

    <section className="chat">
      <div className="day">Сегодня · {scope}</div>
      {messages.map(m=><div key={m.id} className={`row ${m.who}`}>
        {m.who==='assistant' && <div className="mini-orb">✦</div>}
        <div className="bubble">{m.who==='assistant' && <small>{m.agent}</small>}<p>{m.text}</p></div>
      </div>)}
      {busy && <div className="row assistant"><div className="mini-orb">✦</div><div className="bubble typing"><i/><i/><i/></div></div>}
    </section>

    <section className="composer-wrap">
      <div className="quick-actions">
        <button onClick={()=>setOpenAgents(true)}><Bot size={16}/> Специалист</button>
        <button onClick={()=>setOpenMemory(true)}><MessageCircleMore size={16}/> Память</button>
        <button onClick={()=>send(true)} disabled={!text.trim()||busy}><Sparkles size={16}/> Созвать совет</button>
      </div>
      <form className="composer" onSubmit={onSubmit}>
        <button type="button" className="ghost"><Paperclip size={21}/></button>
        <textarea value={text} onChange={e=>setText(e.target.value)} placeholder={placeholder} rows={1} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(false)}}}/>
        <button className="send" disabled={!text.trim()||busy}><Send size={19}/></button>
      </form>
    </section>

    {openMemory && <div className="sheet-backdrop" onClick={()=>setOpenMemory(false)}><section className="sheet" onClick={e=>e.stopPropagation()}>
      <header><div><b>Память · {scope}</b><small>Только твоя память на этом устройстве</small></div><button onClick={()=>setOpenMemory(false)}><X/></button></header>
      <textarea className="memory-editor" value={memory} onChange={e=>setMemory(e.target.value)} placeholder="Например: важные договорённости, правила проекта, предпочтения, текущие цели…"/>
      <button className="memory-save" onClick={()=>setOpenMemory(false)}>Сохранить память</button>
    </section></div>}
  </main>
}