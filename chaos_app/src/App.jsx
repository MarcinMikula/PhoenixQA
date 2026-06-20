/**
 * App.jsx
 *
 * Wires the 3 demo components to the active chaos config.
 * The "Active chaos" panel at the top is a debugging aid for you
 * (and future you) — it makes the invisible (rotating selectors, shadow
 * DOM, delays) visible while developing/inspecting in the browser.
 */
import { getChaosConfigFromEnv } from './chaos/chaosConfig'
import { LoginForm } from './components/LoginForm'
import { TicketList } from './components/TicketList'
import { AddItemForm } from './components/AddItemForm'

function App() {
  const config = getChaosConfigFromEnv()

  return (
    <div className="chaos-app">
      <header>
        <h1>🔥 PhoenixQA Chaos App</h1>
        <p className="chaos-subtitle">
          Intentionally unstable test target. Not a product — a benchmark environment.
        </p>
      </header>

      <div className="chaos-status" data-testid="chaos-status-panel">
        <strong>Active chaos config</strong>
        <ul>
          <li>Level: {config.level}</li>
          <li>Mechanisms: {config.mechanisms.join(', ') || 'none'}</li>
          <li>Shadow DOM: {config.shadowDomEnabled ? 'enabled' : 'disabled'}</li>
        </ul>
      </div>

      <main>
        <LoginForm activeMechanisms={config.mechanisms} />
        <TicketList
          activeMechanisms={config.mechanisms}
          shadowDomEnabled={config.shadowDomEnabled}
        />
        <AddItemForm activeMechanisms={config.mechanisms} />
      </main>
    </div>
  )
}

export default App
