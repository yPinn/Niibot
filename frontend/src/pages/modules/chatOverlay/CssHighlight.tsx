import React from 'react'

const C = {
  comment: 'hsl(220 10% 52%)',
  atRule: 'hsl(270 65% 72%)',
  selector: 'hsl(200 75% 62%)',
  property: 'hsl(175 55% 58%)',
  value: 'hsl(40 10% 82%)',
  important: 'hsl(30 85% 62%)',
  punctuation: 'hsl(220 10% 50%)',
}

function HLine({ line }: { line: string }) {
  const trimmed = line.trimStart()
  const indent = line.slice(0, line.length - trimmed.length)

  if (!trimmed) return <>{line}</>

  if (trimmed.startsWith('/*')) {
    return <span style={{ color: C.comment, fontStyle: 'italic' }}>{line}</span>
  }

  if (trimmed === '}') {
    return (
      <>
        <span>{indent}</span>
        <span style={{ color: C.punctuation }}>{'}'}</span>
      </>
    )
  }

  if (trimmed.startsWith('@')) {
    const m = line.match(/^(\s*)(@[\w-]+)([^{]*)(\{?)$/)
    if (m)
      return (
        <>
          {m[1]}
          <span style={{ color: C.atRule }}>{m[2]}</span>
          <span style={{ color: C.value }}>{m[3]}</span>
          {m[4] && <span style={{ color: C.punctuation }}>{m[4]}</span>}
        </>
      )
  }

  if (/^\s*(from|to)\s*\{/.test(line)) {
    const m = line.match(/^(\s*)(from|to)(\s*)(\{)(.*)(\})/)
    if (m)
      return (
        <>
          {m[1]}
          <span style={{ color: C.atRule }}>{m[2]}</span>
          {m[3]}
          <span style={{ color: C.punctuation }}>{m[4]}</span>
          <span style={{ color: C.value }}>{m[5]}</span>
          <span style={{ color: C.punctuation }}>{m[6]}</span>
        </>
      )
  }

  if (trimmed.endsWith('{') || trimmed.endsWith(',')) {
    const m = line.match(/^(.*?)([{,])\s*$/)
    if (m)
      return (
        <>
          <span style={{ color: C.selector }}>{m[1]}</span>
          <span style={{ color: C.punctuation }}>{m[2]}</span>
        </>
      )
  }

  const propM = line.match(/^(\s*)([\w-]+)(\s*:\s*)(.*?)(\s*!important)?(;)(\s*)$/)
  if (propM) {
    const [, ind, prop, colon, val, imp, semi] = propM
    return (
      <>
        {ind}
        <span style={{ color: C.property }}>{prop}</span>
        <span style={{ color: C.punctuation }}>{colon}</span>
        <span style={{ color: C.value }}>{val}</span>
        {imp && <span style={{ color: C.important }}>{imp}</span>}
        <span style={{ color: C.punctuation }}>{semi}</span>
      </>
    )
  }

  return <>{line}</>
}

export function CssHighlight({ code }: { code: string }) {
  const lines = code.split('\n')
  return (
    <pre className="text-label leading-relaxed whitespace-pre">
      {lines.map((line, i) => (
        <React.Fragment key={i}>
          <HLine line={line} />
          {i < lines.length - 1 && '\n'}
        </React.Fragment>
      ))}
    </pre>
  )
}
