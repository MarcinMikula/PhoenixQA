/**
 * AddItemForm.jsx
 *
 * Primary chaos mechanism here: async_delay. Submitting goes through a
 * simulated network round-trip before the confirmation message appears
 * — this is where a naive `is_visible()` right after `click()` fails,
 * and the healer needs to recognize "not broken, just not ready yet"
 * as a different failure mode than "selector doesn't exist."
 */
import { useMemo, useState } from 'react'
import { rotateSelector } from '../chaos/selectorRotation'
import { useChaosDelay } from '../chaos/asyncDelay'

export function AddItemForm({ activeMechanisms }) {
  const [itemName, setItemName] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const rotationActive = activeMechanisms.includes('selector_rotation')
  const delayActive = activeMechanisms.includes('async_delay')

  const testIds = useMemo(
    () => ({
      input: rotateSelector('item-name', rotationActive),
      submit: rotateSelector('btn-add-item', rotationActive),
      confirmation: rotateSelector('item-added-confirmation', rotationActive),
    }),
    [rotationActive]
  )

  // Ready flips back to true only after the chaos delay elapses following
  // a submit — see useChaosDelay for why `active` is re-evaluated per call.
  const ready = useChaosDelay(submitted && delayActive)

  function handleSubmit(e) {
    e.preventDefault()
    setSubmitted(true)
  }

  const showConfirmation = submitted && (!delayActive || ready)

  return (
    <section className="chaos-add-item">
      <h2>Add item</h2>
      <form onSubmit={handleSubmit}>
        <label htmlFor="chaos-item-name">Item name</label>
        <input
          id="chaos-item-name"
          data-testid={testIds.input}
          value={itemName}
          onChange={(e) => setItemName(e.target.value)}
        />
        <button type="submit" data-testid={testIds.submit}>
          Add item
        </button>
      </form>

      {showConfirmation && (
        <p data-testid={testIds.confirmation}>
          "{itemName}" was added.
        </p>
      )}
    </section>
  )
}
