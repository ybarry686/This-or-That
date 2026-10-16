import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { api } from '../api/client'
import { ErrorMessage, Page } from '../components/ui'
import { saveSession } from '../session'

/** Host recovery link: /r/:code/recover#<recovery token> (the token never reaches server logs). */
export default function Recover() {
  const { code = '' } = useParams()
  const navigate = useNavigate()
  const [error, setError] = useState<unknown>(null)
  const started = useRef(false)

  useEffect(() => {
    // Each recovery rotates the host token, so it must run exactly once.
    if (started.current) return
    started.current = true

    const recoveryToken = window.location.hash.replace(/^#/, '')
    api
      .recoverHost(code, recoveryToken)
      .then((session) => {
        saveSession(session.code, { participantId: session.participant_id, token: session.token })
        navigate(`/r/${session.code}`, { replace: true })
      })
      .catch(setError)
  }, [code, navigate])

  return (
    <Page>
      <h1 className="text-2xl font-bold">Recovering host access…</h1>
      <ErrorMessage error={error} />
    </Page>
  )
}
