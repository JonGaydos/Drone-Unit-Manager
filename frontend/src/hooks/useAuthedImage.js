import { useState, useEffect } from 'react'
import { api } from '@/api/client'

const API_PREFIX = '/api/'

/**
 * A src for an <img> showing a file behind the API's bearer auth. A bare img
 * request carries no Authorization header and gets a 401, so the file is
 * fetched with the session token and shown from a blob: URL, which is revoked
 * when the url changes or the component unmounts.
 * @param {string|null|undefined} url - e.g. "/api/pilots/7/photo/view".
 * @returns {string|null} The blob: URL, a url outside /api/ unchanged, or
 *   null while loading, when the fetch fails, or when there is no url.
 */
export function useAuthedImage(url) {
  const [loaded, setLoaded] = useState({ url: null, src: null })
  const authed = Boolean(url?.startsWith(API_PREFIX))

  useEffect(() => {
    if (!authed) return undefined
    const controller = new AbortController()
    let objectUrl = null
    api.blob(url.slice(API_PREFIX.length - 1), { signal: controller.signal })
      .then((blob) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        setLoaded({ url, src: objectUrl })
      })
      .catch(() => { /* no image: the caller shows its placeholder */ })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [url, authed])

  if (!url) return null
  if (!authed) return url
  return loaded.url === url ? loaded.src : null
}
