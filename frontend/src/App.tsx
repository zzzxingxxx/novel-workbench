import { useEffect, useMemo, useRef, useState } from 'react'
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Command,
  Download,
  FilePlus2,
  FolderOpen,
  History,
  Menu,
  MoreHorizontal,
  PanelRight,
  Play,
  Plus,
  Save,
  Search,
  Send,
  Settings2,
  Sparkles,
  Upload,
  Undo2,
  WandSparkles,
  X,
} from 'lucide-react'

type Chapter = {
  id: string
  title: string
  position: number
  status: string
  content?: string
  content_hash?: string
  word_count?: number
}

type Volume = { id: string; title: string; position: number; chapters: Chapter[] }
type Project = { id: string; name: string; description?: string | null; language: string }
type TreeResponse = { project: Project; volumes: Volume[] }
type Provider = { id: string; name: string; base_url: string; model: string; enabled: boolean }
type PromptTemplate = {
  id: string
  project_id: string | null
  scope: 'global' | 'project' | 'agent' | 'workflow' | 'session'
  owner_id: string | null
  name: string
  enabled: boolean
  active_version_id: string | null
}
type SearchHit = {
  source_type: 'chapter' | 'entity' | 'note'
  source_id: string
  title: string
  snippet: string
  highlight: string
  score: number
  chapter_id: string | null
  volume_id: string | null
  citation: { paragraph: number | null }
}
type LoreEntity = { id: string; name: string; kind: string; status: string; aliases: string[]; description: string; tags: string[] }
type LoreTimeline = { id: string; title: string; absolute_time?: string | null; relative_order?: number | null; time_status: string }
type LoreBranch = { id: string; name: string; status: string; trigger_condition: string }
type LoreForeshadow = { id: string; title: string; status: string; description: string }

function renderSearchHighlight(value: string) {
  return value.split(/(<mark>.*?<\/mark>)/gi).map((part, index) => {
    const match = part.match(/^<mark>(.*?)<\/mark>$/i)
    return match ? <mark key={index}>{match[1]}</mark> : <span key={index}>{part}</span>
  })
}

const demoTree: TreeResponse = {
  project: { id: 'demo-project', name: '潮汐之上', description: '一部关于记忆、航海与重逢的长篇小说。', language: 'zh-CN' },
  volumes: [
    {
      id: 'demo-volume-1',
      title: '第一卷 远岸灯火',
      position: 0,
      chapters: [
        { id: 'demo-chapter-1', title: '一、雾中的信', position: 0, status: 'draft', word_count: 1280 },
        { id: 'demo-chapter-2', title: '二、潮汐表', position: 1, status: 'draft', word_count: 2048 },
        { id: 'demo-chapter-3', title: '三、失真的星图', position: 2, status: 'outline', word_count: 0 },
      ],
    },
    {
      id: 'demo-volume-2',
      title: '第二卷 深海回声',
      position: 1,
      chapters: [{ id: 'demo-chapter-4', title: '四、回声井', position: 0, status: 'outline', word_count: 0 }],
    },
  ],
}

const demoContent = `凌晨四点十七分，灯塔还没有熄灭。

林默把信纸贴在舷窗上。雾气将远处的海面揉成一片灰白，只有那盏灯，每隔七秒从雾里探出一次，像有人在岸边眨眼。

信上没有署名，只有一行被海水晕开的字：

“当潮汐倒流，去找第七码头。”

他已经十年没有回过这座港口。十年前的那场风暴带走了父亲，也带走了他关于那一夜的大部分记忆。` 

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new Error(`API ${response.status}`)
  return response.json() as Promise<T>
}

function App() {
  const [tree, setTree] = useState<TreeResponse>(demoTree)
  const [selectedId, setSelectedId] = useState('demo-chapter-1')
  const [content, setContent] = useState(demoContent)
  const [savedContent, setSavedContent] = useState(demoContent)
  const [savedHash, setSavedHash] = useState<string | undefined>(undefined)
  const [isLoading, setIsLoading] = useState(true)
  const [saveState, setSaveState] = useState<'saved' | 'dirty' | 'saving' | 'offline'>('saved')
  const [assistantTab, setAssistantTab] = useState<'assistant' | 'history'>('assistant')
  const [assistantInput, setAssistantInput] = useState('')
  const [assistantLog, setAssistantLog] = useState<string[]>(['我可以帮你续写、改写选区，或检查本章的节奏与人物状态。'])
  const [openVolumes, setOpenVolumes] = useState<Record<string, boolean>>({ 'demo-volume-1': true, 'demo-volume-2': false })
  const [notice, setNotice] = useState('')
  const [aiSessionId, setAiSessionId] = useState<string | null>(null)
  const [aiStreaming, setAiStreaming] = useState(false)
  const [lastEventId, setLastEventId] = useState(0)
  const eventSourceRef = useRef<EventSource | null>(null)
  const [selectedText, setSelectedText] = useState('')
  const [pendingOperationId, setPendingOperationId] = useState<string | null>(null)
  const [contextExpanded, setContextExpanded] = useState(false)
  const [contextPackage, setContextPackage] = useState<{ used_tokens: number; budget_tokens: number; truncated_count: number; fragments: Array<{ title: string; source: string; token_count: number; content: string; truncated: boolean }> } | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchHit[]>([])
  const [searchBusy, setSearchBusy] = useState(false)
  const [promptOpen, setPromptOpen] = useState(false)
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplate[]>([])
  const [promptSelected, setPromptSelected] = useState<PromptTemplate | null>(null)
  const [promptDraft, setPromptDraft] = useState('')
  const [promptPreview, setPromptPreview] = useState('')
  const [promptBusy, setPromptBusy] = useState(false)
  const [loreOpen, setLoreOpen] = useState(false)
  const [loreTab, setLoreTab] = useState<'entities' | 'timeline' | 'branches' | 'foreshadows'>('entities')
  const [loreData, setLoreData] = useState<{ entities: LoreEntity[]; timeline: LoreTimeline[]; branches: LoreBranch[]; foreshadows: LoreForeshadow[] }>({ entities: [], timeline: [], branches: [], foreshadows: [] })
  const [transferOpen, setTransferOpen] = useState(false)
  const [transferBusy, setTransferBusy] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const selectedChapter = useMemo(
    () => tree.volumes.flatMap((volume) => volume.chapters).find((chapter) => chapter.id === selectedId),
    [tree, selectedId],
  )
  const wordCount = content.replace(/\s/g, '').length

  const openLore = async () => {
    setLoreOpen(true)
    if (tree.project.id === 'demo-project') return
    try {
      const [entities, timeline, branches, foreshadows] = await Promise.all([
        api<LoreEntity[]>(`/api/v1/projects/${tree.project.id}/entities`),
        api<LoreTimeline[]>(`/api/v1/projects/${tree.project.id}/timeline`),
        api<LoreBranch[]>(`/api/v1/projects/${tree.project.id}/branches`),
        api<LoreForeshadow[]>(`/api/v1/projects/${tree.project.id}/foreshadows`),
      ])
      setLoreData({ entities, timeline, branches, foreshadows })
    } catch { setNotice('资料库暂时不可用') }
  }

  const downloadExport = async (format: 'json' | 'zip' | 'markdown' | 'docx' | 'epub') => {
    if (tree.project.id === 'demo-project') {
      setNotice('演示项目尚未连接后端')
      return
    }
    setTransferBusy(true)
    try {
      const response = await fetch(`/api/v1/projects/${tree.project.id}/export?format=${format}`)
      if (!response.ok) throw new Error(`API ${response.status}`)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `novel-workbench-${tree.project.id.slice(0, 8)}.${format === 'markdown' ? 'zip' : format}`
      anchor.click()
      URL.revokeObjectURL(url)
      setNotice('导出已开始')
    } catch {
      setNotice('导出失败，请检查后端状态')
    } finally {
      setTransferBusy(false)
    }
  }

  const importBackup = async (file: File) => {
    setTransferBusy(true)
    try {
      const response = await fetch('/api/v1/projects/import', {
        method: 'POST',
        headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-Filename': file.name },
        body: await file.arrayBuffer(),
      })
      if (!response.ok) throw new Error(`API ${response.status}`)
      const imported = await response.json() as Project
      setNotice(`已导入：${imported.name}`)
      setTransferOpen(false)
    } catch {
      setNotice('导入失败：文件格式或校验和无效')
    } finally {
      setTransferBusy(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  useEffect(() => {
    const load = async () => {
      try {
        const projects = await api<Project[] | { items: Project[] }>('/api/v1/projects?page=1&page_size=1')
        const first = Array.isArray(projects) ? projects[0] : projects.items[0]
        if (!first) throw new Error('empty')
        const loadedTree = await api<TreeResponse>(`/api/v1/projects/${first.id}/tree`)
        setTree(loadedTree)
        const firstChapter = loadedTree.volumes[0]?.chapters[0]
        if (firstChapter) {
          setSelectedId(firstChapter.id)
          const loaded = await api<Chapter>(`/api/v1/chapters/${firstChapter.id}`)
          setContent(loaded.content ?? '')
          setSavedContent(loaded.content ?? '')
          setSavedHash(loaded.content_hash)
        }
      } catch {
        setSaveState('offline')
      } finally {
        setIsLoading(false)
      }
    }
    void load()
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const draft = localStorage.getItem(`novel-workbench:draft:${selectedId}`)
    if (draft && draft !== savedContent) {
      setContent(draft)
      setSaveState('dirty')
    }
  }, [selectedId, savedContent])

  useEffect(() => {
    if (content === savedContent) return
    setSaveState('dirty')
    const timer = window.setTimeout(() => {
      localStorage.setItem(`novel-workbench:draft:${selectedId}`, content)
    }, 400)
    return () => window.clearTimeout(timer)
  }, [content, savedContent, selectedId])

  const selectChapter = async (chapter: Chapter) => {
    setSelectedId(chapter.id)
    setNotice('')
    const cached = localStorage.getItem(`novel-workbench:draft:${chapter.id}`)
    try {
      const loaded = await api<Chapter>(`/api/v1/chapters/${chapter.id}`)
      setContent(loaded.content ?? '')
      setSavedContent(loaded.content ?? '')
      setSavedHash(loaded.content_hash)
      if (cached && cached !== loaded.content) {
        setContent(cached)
        setSaveState('dirty')
      } else {
        setSaveState('saved')
      }
    } catch {
      setContent(cached ?? (chapter.id === 'demo-chapter-1' ? demoContent : ''))
      setSavedContent(chapter.id === 'demo-chapter-1' ? demoContent : '')
      setSavedHash(undefined)
      setSaveState('offline')
    }
  }

  const saveChapter = async () => {
    if (!selectedChapter || content === savedContent) return
    setSaveState('saving')
    try {
      const operation = await api<{ id: string }>('/api/v1/operations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: tree.project.id,
          target_id: selectedChapter.id,
          type: 'replace_range',
          payload: { from: 0, to: savedContent.length, new_text: content },
          old_hash: savedHash,
          idempotency_key: `editor-${selectedChapter.id}-${Date.now()}`,
        }),
      })
      await api(`/api/v1/operations/${operation.id}/approve`, { method: 'POST' })
      const current = await api<Chapter>(`/api/v1/chapters/${selectedChapter.id}`)
      setSavedContent(content)
      setSavedHash(current.content_hash)
      localStorage.removeItem(`novel-workbench:draft:${selectedChapter.id}`)
      setSaveState('saved')
      setNotice('已保存为新版本')
    } catch {
      localStorage.setItem(`novel-workbench:draft:${selectedChapter.id}`, content)
      setSaveState('offline')
      setNotice('已保存到本地草稿，连接后可提交')
    }
  }

  const sendAssistant = () => {
    void sendAssistantMessage()
  }

  const openPromptManager = async () => {
    setPromptOpen(true)
    try {
      const templates = await api<PromptTemplate[]>(`/api/v1/prompts?project_id=${tree.project.id}`)
      setPromptTemplates(templates)
      const first = templates.find((item) => item.scope === 'project') ?? templates[0]
      if (first) {
        setPromptSelected(first)
        const versions = await api<Array<{ content: string }>>(`/api/v1/prompts/${first.id}/versions`)
        setPromptDraft(versions[0]?.content ?? '')
      }
    } catch {
      setNotice('提示词服务暂不可用')
    }
  }

  const runSearch = async () => {
    const query = searchQuery.trim()
    if (!query) return
    setSearchBusy(true)
    try {
      const result = await api<{ items: SearchHit[] }>('/api/v1/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: tree.project.id, query, limit: 30 }),
      })
      setSearchResults(result.items)
    } catch {
      setNotice('搜索暂不可用，请确认后端已启动')
    } finally {
      setSearchBusy(false)
    }
  }

  const openSearchHit = async (hit: SearchHit) => {
    if (hit.chapter_id) {
      const chapter = tree.volumes.flatMap((volume) => volume.chapters).find((item) => item.id === hit.chapter_id)
      if (chapter) await selectChapter(chapter)
    } else {
      setNotice(`${hit.source_type === 'entity' ? '实体' : '笔记'}：${hit.title}`)
    }
    setSearchOpen(false)
  }

  const selectPrompt = async (template: PromptTemplate) => {
    setPromptSelected(template)
    try {
      const versions = await api<Array<{ content: string }>>(`/api/v1/prompts/${template.id}/versions`)
      setPromptDraft(versions[0]?.content ?? '')
    } catch {
      setNotice('无法读取提示词版本')
    }
  }

  const createProjectPrompt = async () => {
    try {
      const created = await api<PromptTemplate>('/api/v1/prompts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope: 'project',
          project_id: tree.project.id,
          name: '项目写作规则',
          content: '围绕《{{project.name}}》的设定进行创作，保持人物和世界观一致。',
          variables: [{ name: 'project.name', required: true }],
        }),
      })
      setPromptTemplates((items) => [...items, created])
      setPromptSelected(created)
      setPromptDraft('围绕《{{project.name}}》的设定进行创作，保持人物和世界观一致。')
    } catch {
      setNotice('提示词创建失败')
    }
  }

  const savePrompt = async () => {
    if (!promptSelected || !promptDraft.trim()) return
    setPromptBusy(true)
    try {
      const updated = await api<PromptTemplate>(`/api/v1/prompts/${promptSelected.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: promptDraft }),
      })
      setPromptSelected(updated)
      setPromptTemplates((items) => items.map((item) => item.id === updated.id ? updated : item))
      setNotice('提示词已保存为新版本')
    } catch {
      setNotice('提示词保存失败')
    } finally {
      setPromptBusy(false)
    }
  }

  const togglePrompt = async (template: PromptTemplate) => {
    try {
      const updated = await api<PromptTemplate>(`/api/v1/prompts/${template.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !template.enabled }),
      })
      setPromptTemplates((items) => items.map((item) => item.id === updated.id ? updated : item))
      if (promptSelected?.id === updated.id) setPromptSelected(updated)
    } catch {
      setNotice('提示词状态更新失败')
    }
  }

  const previewCurrentPrompt = async () => {
    try {
      const result = await api<{ prompt: string }>('/api/v1/prompts/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: tree.project.id, session_prompt: promptDraft }),
      })
      setPromptPreview(result.prompt)
    } catch {
      setNotice('提示词预览失败，请检查变量')
    }
  }

  const cancelAssistant = async () => {
    if (!aiSessionId) return
    eventSourceRef.current?.close()
    eventSourceRef.current = null
    try {
      await api(`/api/v1/ai/sessions/${aiSessionId}/cancel`, { method: 'POST' })
    } finally {
      setAiStreaming(false)
      setAssistantLog((items) => [...items, '已取消本次生成。'])
    }
  }

  const approvePendingOperation = async () => {
    if (!pendingOperationId) return
    try {
      await api(`/api/v1/operations/${pendingOperationId}/approve`, { method: 'POST' })
      if (selectedChapter) {
        const current = await api<Chapter>(`/api/v1/chapters/${selectedChapter.id}`)
        setContent(current.content ?? '')
        setSavedContent(current.content ?? '')
        setSavedHash(current.content_hash)
      }
      setPendingOperationId(null)
      setNotice('AI 建议已写入新版本')
    } catch {
      setNotice('AI 建议审批失败，正文未修改')
    }
  }

  const sendAssistantMessage = async () => {
    const prompt = assistantInput.trim()
    if (!prompt) return
    setAssistantInput('')
    setAssistantLog((items) => [...items, `你：${prompt}`])
    if (tree.project.id.startsWith('demo-')) {
      setAssistantLog((items) => [...items, '建议：先明确这一段的冲突目标，再让林默在动作中暴露记忆缺口。'])
      return
    }
    setAiStreaming(true)
    try {
      let sessionId = aiSessionId
      if (!sessionId) {
        const providers = await api<Provider[]>('/api/v1/providers')
        let provider = providers.find((item) => item.enabled)
        if (!provider) {
          provider = await api<Provider>('/api/v1/providers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: '本地演示 Provider', base_url: 'mock://writer', model: 'demo-1' }),
          })
        }
        const session = await api<{ id: string }>('/api/v1/ai/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: tree.project.id, provider_id: provider.id }),
        })
        sessionId = session.id
        setAiSessionId(sessionId)
      }
      const response = await api<{ message_id: string }>(`/api/v1/ai/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: prompt,
          chapter_id: selectedChapter?.id,
          selected_text: selectedText || undefined,
          idempotency_key: `ui-${sessionId}-${Date.now()}`,
        }),
      })
      const stream = new EventSource(`/api/v1/ai/sessions/${sessionId}/events?last_event_id=${lastEventId}`)
      eventSourceRef.current = stream
      const close = () => { stream.close(); eventSourceRef.current = null; setAiStreaming(false) }
      stream.addEventListener('assistant.delta', (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as { data: { text: string } }
        setLastEventId(Number((event as MessageEvent).lastEventId || 0))
        setAssistantLog((items) => {
          const next = [...items]
          const index = next.length - 1
          if (index >= 0 && next[index].startsWith('AI：')) next[index] += payload.data.text
          else next.push(`AI：${payload.data.text}`)
          return next
        })
      })
      stream.addEventListener('context.ready', () => {
        void api<{ package: typeof contextPackage }>(`/api/v1/ai/sessions/${sessionId}/messages/${response.message_id}/context`)
          .then((result) => setContextPackage(result.package))
          .catch(() => undefined)
      })
      stream.addEventListener('assistant.operation_preview', (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as { data: { operation_id: string } }
        setPendingOperationId(payload.data.operation_id)
        setAssistantLog((items) => [...items, `待审批修改：${payload.data.operation_id.slice(0, 8)}`])
      })
      stream.addEventListener('assistant.failed', (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as { data: { message: string } }
        setAssistantLog((items) => [...items, `AI 错误：${payload.data.message}`])
        close()
      })
      stream.addEventListener('assistant.completed', () => close())
      stream.onerror = () => {
        if (stream.readyState === EventSource.CLOSED) close()
      }
      void response
    } catch {
      setAssistantLog((items) => [...items, 'AI 暂不可用，已保留你的指令。'])
      setAiStreaming(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
          <div className="brand-lockup"><div className="brand-mark"><BookOpen size={16} /></div><span>novel / workbench</span></div>
          <div className="crumbs"><span>{tree.project.name}</span><span className="crumb-slash">/</span><span className="active-crumb">{selectedChapter?.title ?? '选择章节'}</span></div>
        <div className="top-actions">
          <div className={`save-indicator ${saveState}`}><span className="status-dot" />{saveState === 'saved' ? '已保存' : saveState === 'saving' ? '保存中' : saveState === 'offline' ? '本地草稿' : '未保存'}</div>
          <button className="icon-button" title="搜索" onClick={() => setSearchOpen(true)}><Search size={17} /></button>
          <button className="icon-button" title="资料库" onClick={() => void openLore()}><BookOpen size={17} /></button>
          <button className="icon-button" title="导入导出" onClick={() => setTransferOpen(true)}><Download size={17} /></button>
          <button className="icon-button" title="系统提示词" onClick={() => void openPromptManager()}><Settings2 size={17} /></button>
          <div className="avatar">LM</div>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar left-sidebar">
          <div className="sidebar-heading"><span>作品结构</span><button className="icon-button subtle" title="新建"><Plus size={16} /></button></div>
          <div className="project-summary"><div className="project-cover">潮<br />汐</div><div><strong>{tree.project.name}</strong><span>{tree.project.description ?? '本地创作项目'}</span></div></div>
          <div className="tree-actions"><button><FilePlus2 size={14} />新章节</button><button><FolderOpen size={14} />打开项目</button></div>
          <div className="tree-list">
            {tree.volumes.map((volume) => {
              const open = openVolumes[volume.id] ?? true
              return <div className="volume" key={volume.id}>
                <button className="volume-row" onClick={() => setOpenVolumes((state) => ({ ...state, [volume.id]: !open }))}>{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}<span>{volume.title}</span><MoreHorizontal size={15} className="row-more" /></button>
                {open && <div className="chapter-list">{volume.chapters.map((chapter) => <button key={chapter.id} className={`chapter-row ${chapter.id === selectedId ? 'selected' : ''}`} onClick={() => void selectChapter(chapter)}><span className="chapter-index">{String(chapter.position + 1).padStart(2, '0')}</span><span className="chapter-title">{chapter.title.replace(/^\S+、/, '')}</span>{chapter.status === 'outline' ? <span className="outline-tag">提纲</span> : <span className="chapter-count">{chapter.word_count ? `${chapter.word_count}` : '—'}</span>}</button>)}</div>}
              </div>
            })}
          </div>
          <button className="sidebar-footer"><CircleHelp size={16} />工作区指南 <span>⌘ /</span></button>
        </aside>

        <main className="editor-pane">
          <div className="editor-toolbar">
            <div className="toolbar-group"><button className="tool-button" title="撤销"><Undo2 size={16} /></button><button className="tool-button disabled" title="重做"><Undo2 size={16} style={{ transform: 'scaleX(-1)' }} /></button><span className="toolbar-divider" /><button className="tool-button active" title="写作模式"><WandSparkles size={16} />写作</button><button className="tool-button" title="大纲模式"><Command size={16} />大纲</button></div>
            <div className="toolbar-group"><span className="editor-stat">{wordCount.toLocaleString()} 字</span><button className="tool-button" title="历史版本" onClick={() => setAssistantTab('history')}><History size={16} /></button><button className="tool-button save-button" onClick={() => void saveChapter()} title="保存"><Save size={16} />保存版本</button></div>
          </div>
          <div className="editor-scroll">
            <article className="chapter-header"><div className="eyebrow">第一卷 · 远岸灯火</div><h1>{selectedChapter?.title ?? '未命名章节'}</h1><p>草稿 · 最后编辑于今天 04:17</p></article>
            {isLoading ? <div className="loading-state">正在打开作品…</div> : <textarea className="writing-surface" value={content} onChange={(event) => setContent(event.target.value)} onSelect={(event) => { const target = event.currentTarget; setSelectedText(target.value.slice(target.selectionStart, target.selectionEnd)) }} spellCheck={false} aria-label="章节正文" />}
            <div className="editor-bottom"><span><span className="bottom-dot" />自动保存已开启</span><span>Markdown · UTF-8</span></div>
          </div>
        </main>

        <aside className="sidebar right-sidebar">
          <div className="assistant-head"><div className="tab-switch"><button className={assistantTab === 'assistant' ? 'active' : ''} onClick={() => setAssistantTab('assistant')}><Sparkles size={15} />助手</button><button className={assistantTab === 'history' ? 'active' : ''} onClick={() => setAssistantTab('history')}><Clock3 size={15} />版本</button></div><button className="icon-button subtle" title="收起侧栏"><PanelRight size={17} /></button></div>
          {assistantTab === 'assistant' ? <>
            <div className="assistant-context"><div className="context-label">当前上下文</div><div className="context-row"><span className="context-icon"><BookOpen size={14} /></span><span>第 1 章 · 全文</span><span className="context-meta">{wordCount} 字</span></div><div className="context-row"><span className="context-icon violet"><Sparkles size={14} /></span><span>潮汐之上 · 写作规则</span><span className="context-meta">已加载</span></div>{contextPackage && <><button className="context-inspect" onClick={() => setContextExpanded((value) => !value)}><span>{contextExpanded ? '收起 ContextPackage' : '查看 ContextPackage'}</span><ChevronDown size={13} style={{ transform: contextExpanded ? 'rotate(180deg)' : undefined }} /></button>{contextExpanded && <div className="context-package"><div className="context-package-meta">{contextPackage.used_tokens}/{contextPackage.budget_tokens} tokens · 截断 {contextPackage.truncated_count} 段</div>{contextPackage.fragments.map((fragment) => <details key={`${fragment.source}-${fragment.title}`} open><summary>{fragment.title}<span>{fragment.token_count} tokens</span></summary><p>{fragment.content}</p></details>)}</div>}</>}</div>
            <div className="assistant-log">{assistantLog.map((line, index) => <div key={`${line}-${index}`} className={line.startsWith('你：') ? 'user-line' : line.startsWith('建议：') ? 'suggestion-line' : 'assistant-line'}>{line.startsWith('建议：') && <Sparkles size={14} />}{line}</div>)}</div>
            {pendingOperationId && <div className="operation-approval"><div><Sparkles size={14} /><span>AI 已生成一条正文修改建议</span></div><button onClick={() => void approvePendingOperation()}>审批写入</button></div>}
            <div className="quick-prompts"><span>快速操作</span><div><button onClick={() => setAssistantInput('续写这一段，保持克制的悬疑感')}><Play size={13} />续写</button><button onClick={() => setAssistantInput('把这段改得更有画面感')}><WandSparkles size={13} />改写</button><button onClick={() => setAssistantInput('检查人物动机和时间线')}><Search size={13} />检查</button></div></div>
            <div className="assistant-compose"><textarea placeholder={aiStreaming ? '助手正在生成…' : '告诉助手你想做什么…'} value={assistantInput} disabled={aiStreaming} onChange={(event) => setAssistantInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) sendAssistant() }} /><div className="compose-footer"><span>{aiStreaming ? '流式生成中' : '⌘ ↵ 发送'}</span><button className="send-button" onClick={aiStreaming ? () => void cancelAssistant() : sendAssistant} title={aiStreaming ? '取消生成' : '发送'}><Send size={15} /></button></div></div>
          </> : <div className="history-panel"><div className="history-intro"><History size={17} /><div><strong>版本时间线</strong><p>每次审批都会生成一个可恢复版本。</p></div></div><div className="history-item current"><span className="history-dot" /><div><strong>当前草稿</strong><span>今天 04:17 · {wordCount} 字</span></div><MoreHorizontal size={15} /></div><div className="history-item"><span className="history-dot" /><div><strong>初始版本</strong><span>今天 03:52 · 1,280 字</span></div><MoreHorizontal size={15} /></div><button className="history-close" onClick={() => setAssistantTab('assistant')}><X size={14} />返回助手</button></div>}
        </aside>
      </div>
      {searchOpen && <div className="search-overlay" role="dialog" aria-modal="true" aria-label="搜索作品"><div className="search-panel"><div className="search-panel-head"><div><span className="eyebrow">作品检索</span><h2>搜索作品</h2></div><button className="icon-button" title="关闭" onClick={() => setSearchOpen(false)}><X size={17} /></button></div><form className="search-form" onSubmit={(event) => { event.preventDefault(); void runSearch() }}><Search size={16} /><input autoFocus value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="搜索章节、角色、笔记和标签" /><button className="send-button" disabled={searchBusy} title="执行搜索"><Search size={14} /></button></form><div className="search-results">{searchResults.length === 0 && <p className="prompt-empty">输入关键词搜索当前作品。</p>}{searchResults.map((hit) => <button className="search-result" key={`${hit.source_type}-${hit.source_id}`} onClick={() => void openSearchHit(hit)}><div className="search-result-head"><strong>{hit.title}</strong><span>{hit.source_type} · {hit.citation.paragraph ? `第 ${hit.citation.paragraph} 段` : '来源'}</span></div><div className="search-snippet">{renderSearchHighlight(hit.highlight || hit.snippet)}</div></button>)}</div></div></div>}
      {promptOpen && <div className="prompt-overlay" role="dialog" aria-modal="true" aria-label="系统提示词管理">
        <div className="prompt-panel">
          <div className="prompt-panel-head"><div><span className="eyebrow">AI 配置</span><h2>系统提示词</h2></div><button className="icon-button" title="关闭" onClick={() => setPromptOpen(false)}><X size={17} /></button></div>
          <div className="prompt-panel-body">
            <div className="prompt-list"><div className="prompt-list-title"><span className="context-label">已配置模板</span><button className="icon-button subtle" title="新建项目提示词" onClick={() => void createProjectPrompt()}><Plus size={15} /></button></div>{promptTemplates.length === 0 && <p className="prompt-empty">暂无模板，点击加号创建项目规则。</p>}{promptTemplates.map((template) => <button key={template.id} className={`prompt-list-item ${promptSelected?.id === template.id ? 'selected' : ''}`} onClick={() => void selectPrompt(template)}><span><strong>{template.name}</strong><small>{template.scope}</small></span><span className={`prompt-state ${template.enabled ? 'on' : ''}`} onClick={(event) => { event.stopPropagation(); void togglePrompt(template) }}>{template.enabled ? '启用' : '停用'}</span></button>)}</div>
            <div className="prompt-editor"><label>模板正文<textarea value={promptDraft} onChange={(event) => setPromptDraft(event.target.value)} placeholder="例如：你是一个严谨的写作助手。支持 {{project.name}} 等白名单变量。" /></label><div className="prompt-hint">可用变量：project.name、project.description、chapter.title、chapter.content、selected_text、user.instruction、session.prompt</div><div className="prompt-actions"><button className="tool-button" onClick={() => void previewCurrentPrompt()}><Search size={14} />预览最终 Prompt</button><button className="tool-button save-button" disabled={promptBusy || !promptSelected} onClick={() => void savePrompt()}><Save size={14} />保存新版本</button></div>{promptPreview && <pre className="prompt-preview">{promptPreview}</pre>}</div>
          </div>
        </div>
      </div>}
      {loreOpen && <div className="prompt-overlay" role="dialog" aria-modal="true" aria-label="资料库"><div className="prompt-panel lore-panel"><div className="prompt-panel-head"><div><span className="eyebrow">故事资料</span><h2>资料库</h2></div><button className="icon-button" title="关闭" onClick={() => setLoreOpen(false)}><X size={17} /></button></div><div className="lore-tabs">{([['entities', '实体'], ['timeline', '时间线'], ['branches', '分支'], ['foreshadows', '伏笔']] as const).map(([key, label]) => <button key={key} className={loreTab === key ? 'active' : ''} onClick={() => setLoreTab(key)}>{label}</button>)}</div><div className="lore-list">{loreTab === 'entities' && (loreData.entities.length ? loreData.entities.map((item) => <div className="lore-item" key={item.id}><strong>{item.name}</strong><span>{item.kind} · {item.status}</span><p>{item.description || '暂无描述'}{item.aliases?.length ? ` · 别名：${item.aliases.join('、')}` : ''}</p></div>) : <p className="prompt-empty">暂无实体。创建角色、地点或规则后会显示在这里。</p>)}{loreTab === 'timeline' && (loreData.timeline.length ? loreData.timeline.map((item) => <div className="lore-item" key={item.id}><strong>{item.title}</strong><span>{item.time_status} · {item.absolute_time || (item.relative_order == null ? '时间未知' : `顺序 ${item.relative_order}`)}</span></div>) : <p className="prompt-empty">暂无时间线事件。</p>)}{loreTab === 'branches' && (loreData.branches.length ? loreData.branches.map((item) => <div className="lore-item" key={item.id}><strong>{item.name}</strong><span>{item.status}</span><p>{item.trigger_condition || '未设置触发条件'}</p></div>) : <p className="prompt-empty">暂无剧情分支。</p>)}{loreTab === 'foreshadows' && (loreData.foreshadows.length ? loreData.foreshadows.map((item) => <div className="lore-item" key={item.id}><strong>{item.title}</strong><span>{item.status}</span><p>{item.description || '暂无描述'}</p></div>) : <p className="prompt-empty">暂无伏笔。</p>)}</div></div></div>}
      {transferOpen && <div className="prompt-overlay" role="dialog" aria-modal="true" aria-label="导入导出"><div className="prompt-panel transfer-panel"><div className="prompt-panel-head"><div><span className="eyebrow">项目迁移</span><h2>导入 / 导出</h2></div><button className="icon-button" title="关闭" onClick={() => setTransferOpen(false)}><X size={17} /></button></div><div className="transfer-body"><div className="transfer-section"><span className="context-label">导出当前作品</span><div className="transfer-grid"><button className="transfer-action" disabled={transferBusy} onClick={() => void downloadExport('json')}><Download size={15} /><span>JSON 备份</span><small>完整数据</small></button><button className="transfer-action" disabled={transferBusy} onClick={() => void downloadExport('zip')}><Download size={15} /><span>ZIP 项目包</span><small>含校验和</small></button><button className="transfer-action" disabled={transferBusy} onClick={() => void downloadExport('markdown')}><Download size={15} /><span>Markdown</span><small>文件夹结构</small></button><button className="transfer-action" disabled={transferBusy} onClick={() => void downloadExport('docx')}><Download size={15} /><span>DOCX</span><small>文档格式</small></button><button className="transfer-action" disabled={transferBusy} onClick={() => void downloadExport('epub')}><Download size={15} /><span>EPUB</span><small>电子书格式</small></button></div></div><div className="transfer-section transfer-import"><span className="context-label">导入备份或 Markdown 包</span><input ref={fileInputRef} className="transfer-file" type="file" accept=".json,.zip,.md,application/json,application/zip,text/markdown" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importBackup(file) }} /><button className="transfer-upload" disabled={transferBusy} onClick={() => fileInputRef.current?.click()}><Upload size={16} />选择文件</button><p>支持 JSON、ZIP 和 Markdown 文件。导入会创建一个独立作品。</p></div></div></div></div>}
      {notice && <button className="toast" onClick={() => setNotice('')}>{notice}<X size={14} /></button>}
      <button className="mobile-menu" title="菜单"><Menu size={18} /></button>
    </div>
  )
}

export default App
