/**
 * LoginForm.jsx
 *
 * Mirrors the LoginPage Page Object pattern from qa-automation-framework
 * (INPUT_USERNAME, INPUT_PASSWORD, BTN_LOGIN, MSG_ERROR) so the resulting
 * Page Object in PhoenixQA reads almost identically to a real project's.
 *
 * Primary chaos mechanism here: selector_rotation. The testid suffixes
 * rotate on every mount, so a hardcoded [data-testid="username"] locator
 * will work on one run and fail on the next — exactly the scenario the
 * Healer (Sprint 4/5) needs to repair.
 */
import { useMemo, useState } from 'react'
import { rotateSelector } from '../chaos/selectorRotation'
import { DomMutationWrapper } from '../chaos/domMutation'

const VALID_USERNAME = 'admin'
const VALID_PASSWORD = 'secret'

export function LoginForm({ activeMechanisms }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loggedIn, setLoggedIn] = useState(false)

  const rotationActive = activeMechanisms.includes('selector_rotation')
  const mutationActive = activeMechanisms.includes('dom_mutation')

  // useMemo: rotate ONCE per mount, not on every keystroke re-render.
  // See selectorRotation.js for why that distinction matters.
  const testIds = useMemo(
    () => ({
      username: rotateSelector('username', rotationActive),
      password: rotateSelector('password', rotationActive),
      submit: rotateSelector('btn-login', rotationActive),
      error: rotateSelector('login-error', rotationActive),
      welcome: rotateSelector('welcome-message', rotationActive),
    }),
    [rotationActive]
  )

  function handleSubmit(e) {
    e.preventDefault()
    if (username === VALID_USERNAME && password === VALID_PASSWORD) {
      setError('')
      setLoggedIn(true)
    } else {
      setLoggedIn(false)
      setError('Invalid username or password.')
    }
  }

  if (loggedIn) {
    return (
      <p data-testid={testIds.welcome}>
        Welcome, {username}.
      </p>
    )
  }

  return (
    <DomMutationWrapper active={mutationActive}>
      <form onSubmit={handleSubmit} className="chaos-form">
        <h2>Login</h2>

        <label htmlFor="chaos-username">Username</label>
        <input
          id="chaos-username"
          data-testid={testIds.username}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />

        <label htmlFor="chaos-password">Password</label>
        <input
          id="chaos-password"
          type="password"
          data-testid={testIds.password}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button type="submit" data-testid={testIds.submit}>
          Log in
        </button>

        {error && <p data-testid={testIds.error}>{error}</p>}
      </form>
    </DomMutationWrapper>
  )
}
