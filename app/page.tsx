"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  BookOpen,
  Brain,
  Check,
  ChevronRight,
  CirclePause,
  Clock3,
  Focus,
  Hand,
  HeartHandshake,
  Lightbulb,
  MessageCircle,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Sprout,
} from "lucide-react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Activity = {
  title: string;
  time: string;
  text: string;
  skill: string;
};

type StageImage = {
  src: string;
  alt: string;
  caption: string;
};

type AgeStage = {
  id: string;
  label: string;
  title: string;
  lead: string;
  brain: string;
  body: string[];
  adult: string;
  images: StageImage[];
  activities: Activity[];
};

const stages: AgeStage[] = [
  {
    id: "0-1",
    label: "0–1",
    title: "Безопасность и связь",
    lead: "Мозг учится доверять миру через предсказуемый отклик взрослого, голос, взгляд и телесный контакт.",
    brain: "Саморегуляция пока невозможна без взрослого: сначала успокаиваем телом и голосом, потом называем происходящее.",
    body: ["сон и кормление по индивидуальному ритму", "свободное безопасное движение", "минимум лишних раздражителей"],
    adult: "Отвечать на сигналы — не «баловать», а создавать основу будущей устойчивости.",
    images: [
      { src: "/age-0-1-movement.webp", alt: "Младенец двигается на коврике и тянется к контрастной игрушке, пока взрослый находится рядом", caption: "Движение и отклик" },
      { src: "/age-0-1-rhythm.webp", alt: "Взрослый держит младенца на руках и вместе с ним рассматривает книжку-картинку", caption: "Связь и ритуал" },
    ],
    activities: [
      { title: "Лицо и голос", time: "3 мин", text: "Повторяйте звук или мимику ребёнка и ждите его ответа.", skill: "контакт" },
      { title: "Свободное движение", time: "10 мин", text: "Безопасное место на полу: тянуться, поворачиваться, исследовать.", skill: "тело" },
      { title: "Ритуал покоя", time: "5 мин", text: "Одинаковая короткая последовательность перед сном.", skill: "ритм" },
    ],
  },
  {
    id: "1-3",
    label: "1–3",
    title: "Я сам — рядом со взрослым",
    lead: "Речь, движение и самостоятельность растут рывками; сильные чувства часто опережают способность их выразить.",
    brain: "Контроль импульсов только формируется. Нужны короткие правила, повторение и помощь взрослого в остановке.",
    body: ["много движения и сенсорной игры", "устойчивый ритм сна и еды", "пространство для безопасного «сам»"],
    adult: "Дать две приемлемые возможности: «красная чашка или синяя?» — и спокойно удержать границу.",
    images: [
      { src: "/age-1-3-choice.webp", alt: "Малыш выбирает одну из двух футболок, а взрослый спокойно ждёт решения", caption: "Простой выбор" },
      { src: "/age-1-3-help.webp", alt: "Малыш самостоятельно несёт салфетки к семейному столу", caption: "Настоящая помощь" },
    ],
    activities: [
      { title: "Два выбора", time: "2 мин", text: "Предлагайте ребёнку выбрать один из двух подходящих вариантов.", skill: "решение" },
      { title: "Несу сам", time: "5 мин", text: "Поручите отнести салфетки, носки или небьющуюся чашку.", skill: "самообслуживание" },
      { title: "Стоп — идём", time: "7 мин", text: "Играйте в остановку и движение под хлопки или музыку.", skill: "самоконтроль" },
    ],
  },
  {
    id: "3-5",
    label: "3–5",
    title: "Воображение, правила и первые стратегии",
    lead: "В этом возрасте ребёнок учится удерживать простую цель, договариваться, замечать чувства и пробовать делать самому.",
    brain: "Самоконтроль тренируется в игре: дождаться сигнала, сменить правило, вспомнить последовательность — это работа исполнительных функций.",
    body: ["сон 10–13 часов за сутки", "не менее 180 минут движения в течение дня", "экран — до 1 часа качественного контента со взрослым"],
    adult: "Сначала соединиться и назвать чувство, затем коротко напомнить границу и предложить допустимое действие.",
    images: [
      { src: "/age-3-5-emotions.webp", alt: "Дошкольник вместе со взрослым делает спокойный вдох и замечает своё чувство", caption: "Пауза и эмоции" },
      { src: "/age-3-5-play.webp", alt: "Дошкольник самостоятельно строит воображаемый город из открытых материалов", caption: "Своя игра" },
    ],
    activities: [
      { title: "Светофор эмоций", time: "5 мин", text: "Стоп. Назови чувство. Выбери: подышать, попросить помощь или отойти.", skill: "эмоции" },
      { title: "Замри — отомри", time: "8 мин", text: "Двигайтесь под музыку и замирайте, когда она остановится.", skill: "внимание" },
      { title: "Моя полезная миссия", time: "10 мин", text: "Пусть ребёнок сам выберет дело: полить цветок, разобрать носки или накрыть на стол.", skill: "самостоятельность" },
    ],
  },
  {
    id: "5-7",
    label: "5–7",
    title: "План, сотрудничество и готовность учиться",
    lead: "Ребёнок уже может держать 2–3 шага инструкции, но игра, движение и поддержка взрослого всё ещё важнее ранней «взрослости».",
    brain: "Полезны игры с правилами, сменой ролей, памятью и гибкостью — без перегрузки занятиями.",
    body: ["стабильный сон и паузы после нагрузки", "ежедневная активная игра", "чередование концентрации и движения"],
    adult: "Не делать вместо ребёнка, а помогать составить короткий план и замечать усилие.",
    images: [
      { src: "/age-5-7-plan.webp", alt: "Ребёнок собирает рюкзак по последовательности из трёх картинок", caption: "План из трёх шагов" },
      { src: "/age-5-7-cooperation.webp", alt: "Двое детей вместе строят мост из деревянных деталей и проверяют результат", caption: "Общая задача" },
    ],
    activities: [
      { title: "План из трёх шагов", time: "5 мин", text: "Нарисуйте: сначала, потом, готово — и следуйте картинкам.", skill: "планирование" },
      { title: "Наоборот", time: "7 мин", text: "На «день» закрыть глаза, на «ночь» открыть — затем сменить правило.", skill: "гибкость" },
      { title: "Сам выбрал дело", time: "15 мин", text: "Ребёнок придумывает полезную задачу и доводит её до видимого результата.", skill: "инициатива" },
    ],
  },
  {
    id: "7-10",
    label: "7–10",
    title: "Компетентность и собственная зона ответственности",
    lead: "Учёба, дружба и сравнение с другими становятся важнее; ребёнку нужны опыт успеха и право ошибаться.",
    brain: "Планирование укрепляется, когда ребёнок видит объём дела, делит его на части и сам отмечает результат.",
    body: ["достаточный сон и движение каждый день", "перерывы между учебными блоками", "реальная бытовая ответственность"],
    adult: "Разбирать не личность ребёнка, а ситуацию: что получилось, где остановился, какой следующий шаг.",
    images: [
      { src: "/age-7-10-focus.webp", alt: "Школьник делит творческую работу на небольшие шаги и выбирает первый", caption: "Один шаг сейчас" },
      { src: "/age-7-10-responsibility.webp", alt: "Ребёнок самостоятельно насыпает корм и наливает воду семейной собаке", caption: "Зона ответственности" },
    ],
    activities: [
      { title: "Один шаг сейчас", time: "10 мин", text: "Большую задачу разделите и выберите только первый выполнимый шаг.", skill: "фокус" },
      { title: "Домашняя роль", time: "15 мин", text: "Закрепите постоянную задачу, результат которой нужен всей семье.", skill: "ответственность" },
      { title: "Разбор без оценки", time: "5 мин", text: "Что хотел? Что сделал? Что помогло? Что попробую иначе?", skill: "самоанализ" },
    ],
  },
  {
    id: "10-13",
    label: "10–13",
    title: "Перестройка, принадлежность и уважение к границам",
    lead: "Начало пубертата может усиливать чувствительность и утомляемость. Потребность в самостоятельности растёт быстрее навыков управления собой.",
    brain: "Нужны внешние опоры для планирования и уважительный разговор без публичного стыда и длинных нотаций.",
    body: ["сон как защищённая часть расписания", "регулярное движение без культа результата", "личное пространство и предсказуемые правила"],
    adult: "Согласовать границы заранее: что ребёнок решает сам, что обсуждается, а что остаётся обязанностью взрослого.",
    images: [
      { src: "/age-10-13-balance.webp", alt: "Подросток распределяет цветные блоки нагрузки и отдыха на недельном плане", caption: "Баланс нагрузки" },
      { src: "/age-10-13-task.webp", alt: "Подросток самостоятельно чинит устойчивость подставки для растений", caption: "Конструктивная задача" },
    ],
    activities: [
      { title: "Карта нагрузки", time: "10 мин", text: "Отметьте дела, отдых и один блок без обязательств.", skill: "баланс" },
      { title: "Пауза перед ответом", time: "3 мин", text: "Условный знак помогает взять минуту и вернуться к разговору.", skill: "самоконтроль" },
      { title: "Моя конструктивная задача", time: "20 мин", text: "Выбрать небольшую проблему дома и предложить рабочее решение.", skill: "инициатива" },
    ],
  },
  {
    id: "13-17",
    label: "13–17",
    title: "Идентичность, выбор и последствия",
    lead: "Подросток строит собственную систему ценностей. Контакт сохраняется там, где есть уважение, ясные границы и настоящее влияние на решения.",
    brain: "Планирование и торможение импульса продолжают развиваться; риск и сильные эмоции требуют заранее продуманных безопасных сценариев.",
    body: ["сон, движение и питание без морализаторства", "время без цифрового шума", "доступ к надёжному взрослому"],
    adult: "Не допрашивать, а договариваться: факты, риск, выбор, последствия и возможность безопасно выйти из ситуации.",
    images: [
      { src: "/age-13-17-boundaries.webp", alt: "Старший подросток спокойно выходит из некомфортной компании в безопасное пространство", caption: "Граница и выход" },
      { src: "/age-13-17-project.webp", alt: "Подросток самостоятельно завершает проект по ремонту велосипеда и проверяет результат", caption: "Проект с результатом" },
    ],
    activities: [
      { title: "План Б", time: "10 мин", text: "Заранее придумать, как уйти из небезопасной компании без потери лица.", skill: "границы" },
      { title: "Разбор решения", time: "7 мин", text: "Факты, чувства, варианты, последствия, следующий шаг.", skill: "самоанализ" },
      { title: "Проект с результатом", time: "30 мин", text: "Выбрать реальную задачу и самостоятельно определить критерий готовности.", skill: "агентность" },
    ],
  },
];

const skillCards = [
  { icon: CirclePause, title: "Самоконтроль", text: "Остановиться, выдержать короткое ожидание и выбрать действие вместо импульса.", practice: "Игры «стоп — иди», очередность, пауза перед ответом.", color: "blue" },
  { icon: HeartHandshake, title: "Управление эмоциями", text: "Замечать чувство, безопасно проживать его и знать, что помогает успокоиться.", practice: "Название чувства + телесная стратегия + поддержка.", color: "orange" },
  { icon: Focus, title: "Управление вниманием", text: "Возвращаться к задаче, переключаться по сигналу и отсеивать лишнее.", practice: "Короткий фокус, движение, ещё один короткий фокус.", color: "mint" },
  { icon: Hand, title: "Самообслуживание", text: "Делать посильные действия с телом, одеждой, едой и своим пространством.", practice: "Не исправлять сразу; дать время закончить самому.", color: "yellow" },
  { icon: Sparkles, title: "Умение себя занять", text: "Выбрать занятие без постоянной подачи идей и выдержать самостоятельную игру.", practice: "Коробка открытых материалов и спокойный старт рядом.", color: "orange" },
  { icon: Lightbulb, title: "Конструктивная задача", text: "Заметить, что можно улучшить, придумать результат и первый шаг.", practice: "«Что здесь нужно сделать? Как поймём, что готово?»", color: "yellow" },
  { icon: Search, title: "Самоанализ", text: "Отделять факт от оценки: что произошло, что я сделал и что попробую иначе.", practice: "Короткий разбор после успокоения, без стыда.", color: "mint" },
  { icon: MessageCircle, title: "Войти и выйти из общения", text: "Поздороваться, предложить игру, услышать отказ, обозначить границу и безопасно уйти.", practice: "Ролевые репетиции фраз до реальной ситуации.", color: "blue" },
];

const difficulties = [
  {
    title: "Истерика или очень сильное чувство",
    before: "Уменьшите слова и раздражители, оставайтесь рядом, проверьте безопасность.",
    say: "«Тебе очень трудно. Я рядом. Бить нельзя. Можно топнуть или сжать подушку».",
    after: "Когда тело успокоилось: назвать триггер, восстановить ущерб и выбрать план на следующий раз.",
  },
  {
    title: "Ребёнок бьёт, кусает или толкает",
    before: "Сразу физически остановите действие без угроз и унижения.",
    say: "«Я не дам бить. Ты злишься. Отойдём. Скажи: стоп, это моё».",
    after: "Помочь пострадавшему, затем потренировать допустимую фразу и действие.",
  },
  {
    title: "Не хочет уходить с площадки",
    before: "Предупредите заранее и покажите переход: ещё два действия, затем уходим.",
    say: "«Хочется остаться. Пора уходить. Последний спуск — сам или со мной?»",
    after: "Не отменять границу из-за протеста; отметить, что ребёнок смог перейти.",
  },
  {
    title: "Не хочет убирать или делать сам",
    before: "Сократите объём до видимого маленького результата и начните рядом.",
    say: "«Ты собираешь кубики, я — книги. С чего начнёшь: с красных или с больших?»",
    after: "Оценить конкретное действие, а не ярлык: «Ты довёл полку до порядка».",
  },
  {
    title: "Не умеет занять себя без взрослого",
    before: "Подготовьте 2–3 знакомых открытых материала, уберите лишнее.",
    say: "«Я начну с тобой пять минут, потом займусь делом. Ты можешь продолжить или выбрать другое».",
    after: "Увеличивать самостоятельное время постепенно, не требовать сразу долгой игры.",
  },
  {
    title: "Трудно войти в игру или выйти из общения",
    before: "Заранее разыграйте две фразы входа, отказа и безопасного ухода.",
    say: "«Можно с вами? Что я могу делать?» / «Мне так не подходит. Я ухожу к взрослому».",
    after: "Обсудить факты без допроса: что заметил, что сказал, что сработало.",
  },
];

const books = [
  { title: "«Как говорить, чтобы дети слушали…»", author: "Адель Фабер, Элейн Мазлиш", use: "Фразы для чувств, границ, сотрудничества и решения конфликтов." },
  { title: "«Взрывной ребёнок»", author: "Росс Грин", use: "Когда повторяются вспышки и требования не работают: совместный поиск решения." },
  { title: "«Саморег»", author: "Стюарт Шанкер", use: "Как отличать плохое поведение от перегрузки и снижать лишний стресс." },
  { title: "«Воспитание с умом»", author: "Дэниел Сигел, Тина Пэйн Брайсон", use: "Понятная модель мозга и восстановление контакта после сильных эмоций." },
  { title: "«Тайная опора»", author: "Людмила Петрановская", use: "Привязанность, взросление и роль надёжного взрослого на разных этапах." },
  { title: "«Хорошие внутри»", author: "Бекки Кеннеди", use: "Твёрдые границы без стыда и взгляд на трудность как на недостающий навык." },
];

const publicBasePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

function storageKey(stageId: string) {
  const today = new Date().toISOString().slice(0, 10);
  return `rastem-vmeste:${today}:${stageId}`;
}

export default function Home() {
  const [stageId, setStageId] = useState("3-5");
  const [done, setDone] = useState<number[]>([]);
  const stage = useMemo(
    () => stages.find((item) => item.id === stageId) ?? stages[2],
    [stageId],
  );

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(storageKey(stageId));
      setDone(saved ? JSON.parse(saved) : []);
    } catch {
      setDone([]);
    }
  }, [stageId]);

  function toggleActivity(index: number) {
    const next = done.includes(index)
      ? done.filter((item) => item !== index)
      : [...done, index];
    setDone(next);
    window.localStorage.setItem(storageKey(stageId), JSON.stringify(next));
  }

  function resetDay() {
    setDone([]);
    window.localStorage.removeItem(storageKey(stageId));
  }

  const progress = Math.round((done.length / stage.activities.length) * 100);

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Растём вместе — в начало">
          <span className="brand-mark"><Sprout aria-hidden="true" /></span>
          <span>Растём вместе</span>
        </a>
        <nav className="topnav" aria-label="Основные разделы">
          <a href="#today">Сегодня</a>
          <a href="#skills">Навыки</a>
          <a href="#difficulties">Сложные моменты</a>
          <a href="#library">Родителю</a>
        </nav>
        <span className="evidence-badge"><ShieldCheck aria-hidden="true" /> Без стыда и наказаний</span>
      </header>

      <div className="site-shell" id="top">
        <section className="age-picker" aria-labelledby="age-heading">
          <div>
            <p className="eyebrow">Навигатор развития</p>
            <h1 id="age-heading">Что важно ребёнку сейчас</h1>
          </div>
          <Tabs value={stageId} onValueChange={setStageId} className="age-tabs">
            <TabsList className="age-tabs-list" aria-label="Выберите возраст ребёнка">
              {stages.map((item) => (
                <TabsTrigger key={item.id} value={item.id} className="age-tab">
                  {item.label} <span>лет</span>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <p className="orientation-note">Возраст — ориентир, а не экзамен. Темп развития у детей различается.</p>
        </section>

        <section className="hero-grid" aria-live="polite">
          <div className="stage-card">
            <div className="stage-copy">
              <span className="stage-number">Этап {stage.label} лет</span>
              <h2>{stage.title}</h2>
              <p className="stage-lead">{stage.lead}</p>
              <div className="brain-note">
                <Brain aria-hidden="true" />
                <p><strong>Что тренирует мозг.</strong> {stage.brain}</p>
              </div>
              <div className="body-needs">
                <p>Физиологическая опора</p>
                <ul>
                  {stage.body.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </div>
            <div className="hero-art" aria-label={`Иллюстрации для возраста ${stage.label} лет`}>
              <div className="stage-gallery" key={stage.id}>
                {stage.images.map((item, index) => (
                  <figure className={`stage-image stage-image-${index + 1}`} key={item.src}>
                    <Image
                      src={`${publicBasePath}${item.src}`}
                      alt={item.alt}
                      fill
                      priority={index === 0}
                      sizes={index === 0 ? "(max-width: 900px) 100vw, 44vw" : "(max-width: 900px) 46vw, 19vw"}
                    />
                    <figcaption>{item.caption}</figcaption>
                  </figure>
                ))}
              </div>
              <div className="adult-tip">
                <span>Опора взрослого</span>
                <p>{stage.adult}</p>
              </div>
            </div>
          </div>

          <aside className="today-card" id="today">
            <div className="today-heading">
              <div>
                <p className="eyebrow">Маленькие шаги</p>
                <h2>План на сегодня</h2>
              </div>
              <span className="score">{done.length}/{stage.activities.length}</span>
            </div>
            <Progress value={progress} aria-label={`Выполнено ${progress}% плана`} className="daily-progress" />
            <div className="activity-list">
              {stage.activities.map((activity, index) => {
                const checked = done.includes(index);
                return (
                  <label className={`activity ${checked ? "is-done" : ""}`} key={activity.title}>
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => toggleActivity(index)}
                      aria-label={`Отметить занятие «${activity.title}»`}
                      className="activity-check"
                    />
                    <span className="activity-copy">
                      <span className="activity-title">{activity.title}</span>
                      <span className="activity-text">{activity.text}</span>
                      <span className="activity-meta"><Clock3 aria-hidden="true" /> {activity.time} · {activity.skill}</span>
                    </span>
                  </label>
                );
              })}
            </div>
            <Button variant="ghost" size="sm" onClick={resetDay} className="reset-button" disabled={done.length === 0}>
              <RotateCcw aria-hidden="true" /> Сбросить отметки
            </Button>
          </aside>
        </section>

        <section className="content-section" id="skills">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Навыки на всю жизнь</p>
              <h2>Не требуем — последовательно тренируем</h2>
            </div>
            <p>Навык растёт там, где ребёнок получает посильную задачу, ясную границу, право на ошибку и возможность попробовать снова.</p>
          </div>
          <div className="skills-grid">
            {skillCards.map((skill) => {
              const Icon = skill.icon;
              return (
                <article className={`skill-card ${skill.color}`} key={skill.title}>
                  <span className="skill-icon"><Icon aria-hidden="true" /></span>
                  <h3>{skill.title}</h3>
                  <p>{skill.text}</p>
                  <div className="practice"><Check aria-hidden="true" /> <span>{skill.practice}</span></div>
                </article>
              );
            })}
          </div>
        </section>

        <section className="content-section difficulty-section" id="difficulties">
          <div className="difficulty-intro">
            <p className="eyebrow">Когда трудно прямо сейчас</p>
            <h2>Сначала безопасность и контакт. Обучение — после успокоения.</h2>
            <p>Сильное поведение часто означает: ребёнок пока не справился доступным ему способом. Граница остаётся твёрдой, отношение — уважительным.</p>
            <div className="formula">
              <span>1</span> Остановить вред
              <ChevronRight aria-hidden="true" />
              <span>2</span> Назвать чувство
              <ChevronRight aria-hidden="true" />
              <span>3</span> Дать допустимый способ
            </div>
          </div>
          <div className="difficulty-list">
            <Accordion type="single" collapsible defaultValue="item-0">
              {difficulties.map((item, index) => (
                <AccordionItem value={`item-${index}`} key={item.title} className="difficulty-item">
                  <AccordionTrigger className="difficulty-trigger">{item.title}</AccordionTrigger>
                  <AccordionContent>
                    <div className="response-steps">
                      <div><span>Сначала</span><p>{item.before}</p></div>
                      <div><span>Можно сказать</span><p>{item.say}</p></div>
                      <div><span>После</span><p>{item.after}</p></div>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </section>

        <section className="content-section parent-tool" aria-labelledby="reflection-heading">
          <div className="reflection-card">
            <div className="reflection-icon"><Search aria-hidden="true" /></div>
            <p className="eyebrow">Вечерний самоанализ без оценки</p>
            <h2 id="reflection-heading">Четыре вопроса вместо «как ты себя вёл?»</h2>
            <ol>
              <li><span>01</span> Что сегодня произошло?</li>
              <li><span>02</span> Что ты почувствовал и чего хотел?</li>
              <li><span>03</span> Что помогло хотя бы немного?</li>
              <li><span>04</span> Что попробуем в следующий раз?</li>
            </ol>
          </div>
          <div className="communication-card">
            <p className="eyebrow">Коммуникация и границы</p>
            <h2>Фразы, которые можно репетировать</h2>
            <div className="phrase-list">
              <div><span>Войти</span><p>«Можно с вами? Что я могу делать?»</p></div>
              <div><span>Договориться</span><p>«Давай по очереди. Кто будет первым?»</p></div>
              <div><span>Отказать</span><p>«Нет, я не хочу. Давай по-другому».</p></div>
              <div><span>Выйти</span><p>«Мне так не подходит. Я ухожу к взрослому».</p></div>
            </div>
          </div>
        </section>

        <section className="content-section" id="library">
          <div className="section-heading library-heading">
            <div>
              <p className="eyebrow">Педагогическая библиотека</p>
              <h2>Что читать под конкретную трудность</h2>
            </div>
            <p>Не список «идеального родителя», а понятные подходы к эмоциям, границам, перегрузке и сотрудничеству.</p>
          </div>
          <div className="book-grid">
            {books.map((book, index) => (
              <article className="book-card" key={book.title}>
                <div className="book-spine"><span>{String(index + 1).padStart(2, "0")}</span><BookOpen aria-hidden="true" /></div>
                <div>
                  <h3>{book.title}</h3>
                  <p className="author">{book.author}</p>
                  <p>{book.use}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="sources" aria-labelledby="sources-heading">
          <div>
            <p className="eyebrow">Проверяемая основа</p>
            <h2 id="sources-heading">Источники и важные оговорки</h2>
            <p>Материалы помогают выбирать повседневные действия, но не ставят диагноз и не заменяют врача, психолога или специалиста по развитию. Если ребёнок потерял уже освоенный навык или вас тревожит развитие, обсудите это со специалистом.</p>
          </div>
          <div className="source-links">
            <a href="https://www.cdc.gov/act-early/milestones/4-years.html" target="_blank" rel="noreferrer">CDC: ориентиры развития в 4 года <ArrowUpRight /></a>
            <a href="https://developingchild.harvard.edu/resource-guides/guide-executive-function/" target="_blank" rel="noreferrer">Harvard: исполнительные функции <ArrowUpRight /></a>
            <a href="https://www.who.int/publications/i/item/9789241550536" target="_blank" rel="noreferrer">ВОЗ: сон, движение и экран до 5 лет <ArrowUpRight /></a>
            <a href="https://www.who.int/news-room/fact-sheets/detail/physical-activity" target="_blank" rel="noreferrer">ВОЗ: физическая активность <ArrowUpRight /></a>
          </div>
        </section>
      </div>

      <footer>
        <div className="brand"><span className="brand-mark"><Sprout aria-hidden="true" /></span><span>Растём вместе</span></div>
        <p>Развитие — не гонка за навыками. Это постепенное появление внутренней опоры.</p>
      </footer>
    </main>
  );
}
