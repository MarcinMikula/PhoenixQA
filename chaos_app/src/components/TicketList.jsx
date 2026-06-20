/**
 * TicketList.jsx
 *
 * Primary chaos mechanism here: shadow_dom (independent flag).
 * Also exercises dom_mutation since table rows are a common place for
 * wrapper-element changes (e.g. a <tr> migrating to a styled <div> grid row).
 *
 * Deliberately simple data — a handful of fake support tickets, not a
 * real ticketing system. The point is locator stability, not realistic
 * business data.
 */
import { useMemo } from 'react'
import { rotateSelector } from '../chaos/selectorRotation'
import { DomMutationWrapper } from '../chaos/domMutation'
import { ShadowDomWrapper } from '../chaos/shadowDom'

const SAMPLE_TICKETS = [
  { id: 'TCK-001', title: 'Login button unresponsive', status: 'Open' },
  { id: 'TCK-002', title: 'Invoice PDF missing logo', status: 'In Progress' },
  { id: 'TCK-003', title: 'Dashboard chart not loading', status: 'Closed' },
]

export function TicketList({ activeMechanisms, shadowDomEnabled }) {
  const rotationActive = activeMechanisms.includes('selector_rotation')
  const mutationActive = activeMechanisms.includes('dom_mutation')

  const testIds = useMemo(
    () => ({
      table: rotateSelector('ticket-table', rotationActive),
      row: (id) => rotateSelector(`ticket-row-${id}`, rotationActive),
    }),
    [rotationActive]
  )

  return (
    <ShadowDomWrapper active={shadowDomEnabled}>
      <DomMutationWrapper active={mutationActive}>
        <section className="chaos-tickets">
          <h2>Support tickets</h2>
          <table data-testid={testIds.table}>
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {SAMPLE_TICKETS.map((ticket) => (
                <tr key={ticket.id} data-testid={testIds.row(ticket.id)}>
                  <td>{ticket.id}</td>
                  <td>{ticket.title}</td>
                  <td>{ticket.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </DomMutationWrapper>
    </ShadowDomWrapper>
  )
}
