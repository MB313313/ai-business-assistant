import { useEffect, useMemo, useRef } from 'react'

type Props = {
  files: File[]
  onChange: (files: File[]) => void
}

const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/gif'])

function isSupportedImage(f: File): boolean {
  return IMAGE_TYPES.has((f.type || '').toLowerCase())
}

export function AttachmentPicker({ files, onChange }: Props) {
  const supported = useMemo(() => files.filter(isSupportedImage), [files])
  const urlsRef = useRef<string[]>([])

  useEffect(() => {
    // Revoke any previously created object URLs to avoid leaks.
    urlsRef.current.forEach((u) => URL.revokeObjectURL(u))
    urlsRef.current = []
  }, [supported])

  return (
    <div>
      <div className="rowWrap">
        <label className="btn" style={{ borderRadius: 12 }}>
          Add images
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            style={{ display: 'none' }}
            onChange={(e) => {
              const list = Array.from(e.target.files ?? [])
              onChange(list)
              e.currentTarget.value = ''
            }}
          />
        </label>
        {files.length > 0 ? (
          <button type="button" className="btn" onClick={() => onChange([])}>
            Clear files
          </button>
        ) : null}
        {files.length > 0 && supported.length !== files.length ? (
          <span className="statusWarn">Only images are supported right now.</span>
        ) : null}
      </div>

      {supported.length ? (
        <div className="chipRow">
          {supported.map((f) => {
            const url = URL.createObjectURL(f)
            urlsRef.current.push(url)
            return (
              <div key={`${f.name}-${f.size}-${f.lastModified}`} className="chip">
                <img className="chipImg" src={url} alt="" />
                <div className="chipText">
                  <div className="chipName">{f.name}</div>
                  <div className="chipSub">Image</div>
                </div>
              </div>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

