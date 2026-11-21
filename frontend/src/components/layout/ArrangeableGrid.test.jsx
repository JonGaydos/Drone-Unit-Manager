import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ArrangeableGrid from './ArrangeableGrid'
import { resolveLayout } from './resolveLayout'

function tile(id, label, extra = {}) {
  return { id, label, span: 'lg:col-span-3', render: () => <section aria-label={label}><h3>{label}</h3></section>, ...extra }
}

const TILES = [tile('alpha', 'Alpha'), tile('bravo', 'Bravo'), tile('charlie', 'Charlie')]

/** The tile names in the order they are on the page. */
function shownOrder() {
  return screen.queryAllByRole('heading', { level: 3 }).map(h => h.textContent)
}

function renderGrid(props = {}) {
  const onSave = vi.fn().mockResolvedValue(undefined)
  const onSaveDefault = vi.fn().mockResolvedValue(undefined)
  const user = userEvent.setup()
  render(<ArrangeableGrid tiles={TILES} layout={null} defaultLayout={null}
    onSave={onSave} onSaveDefault={onSaveDefault} {...props} />)
  return { user, onSave, onSaveDefault }
}

// jsdom lays nothing out. Give each tile a box by its place on the page, one
// tile per row, so dnd-kit's keyboard sensor can find the tile below.
let rectSpy
beforeEach(() => {
  rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function rect() {
    const cell = this.closest('[data-tile-id]')
    const index = cell ? [...cell.parentElement.children].indexOf(cell) : 0
    const top = index * 100
    return { x: 0, y: top, top, left: 0, width: 200, height: 80, right: 200, bottom: top + 80, toJSON: () => ({}) }
  })
})
afterEach(() => rectSpy.mockRestore())

describe('resolveLayout', () => {
  it('ignores unknown ids and appends new tiles, switched on', () => {
    const resolved = resolveLayout(TILES, { order: ['charlie', 'retired', 'alpha'], hidden: ['retired', 'alpha'] })
    expect(resolved).toEqual({ order: ['charlie', 'alpha', 'bravo'], hidden: ['alpha'] })
  })

  it('keeps the tiles in their given order with no layout', () => {
    expect(resolveLayout(TILES, null)).toEqual({ order: ['alpha', 'bravo', 'charlie'], hidden: [] })
  })
})

describe('ArrangeableGrid', () => {
  it('shows the tiles in the saved order and leaves switched-off tiles out', () => {
    renderGrid({ layout: { order: ['charlie', 'alpha', 'bravo'], hidden: ['bravo'] } })
    expect(shownOrder()).toEqual(['Charlie', 'Alpha'])
  })

  it('uses the unit default when the user has no layout of their own', () => {
    renderGrid({ defaultLayout: { order: ['bravo', 'alpha', 'charlie'], hidden: [] } })
    expect(shownOrder()).toEqual(['Bravo', 'Alpha', 'Charlie'])
  })

  it('ignores unknown ids and shows a new tile at the end', () => {
    renderGrid({ layout: { order: ['gone', 'charlie', 'alpha'], hidden: ['gone'] } })
    expect(shownOrder()).toEqual(['Charlie', 'Alpha', 'Bravo'])
  })

  it('never shows a tile the user has no permission for, even when editing', async () => {
    const tiles = [...TILES, tile('secret', 'Secret', { visible: false })]
    const { user } = renderGrid({ tiles, layout: { order: ['secret', 'alpha'], hidden: [] } })
    expect(screen.queryByRole('heading', { name: 'Secret' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    expect(screen.queryByRole('heading', { name: 'Secret' })).toBeNull()
    expect(screen.queryByRole('switch', { name: 'Show Secret' })).toBeNull()
  })

  it('switches a tile off and saves the layout', async () => {
    const { user, onSave } = renderGrid()
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    const toggle = screen.getByRole('switch', { name: 'Show Bravo' })
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith({ order: ['alpha', 'bravo', 'charlie'], hidden: ['bravo'] })
  })

  it('leaves edit mode after a save', async () => {
    const { user } = renderGrid()
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('button', { name: 'Edit layout' })).toBeInTheDocument()
  })

  it('switches a hidden tile back on', async () => {
    const { user, onSave } = renderGrid({ layout: { order: ['alpha', 'bravo', 'charlie'], hidden: ['charlie'] } })
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    await user.click(screen.getByRole('switch', { name: 'Show Charlie' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith({ order: ['alpha', 'bravo', 'charlie'], hidden: [] })
  })

  it('moves a tile with the keyboard', async () => {
    const { user, onSave } = renderGrid()
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    screen.getByRole('button', { name: 'Move Alpha' }).focus()
    await user.keyboard(' ')
    await act(() => new Promise(resolve => setTimeout(resolve, 0)))
    await user.keyboard('{ArrowDown}')
    await act(() => new Promise(resolve => setTimeout(resolve, 0)))
    await user.keyboard(' ')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith({ order: ['bravo', 'alpha', 'charlie'], hidden: [] })
  })

  it('cancel drops the changes', async () => {
    const { user, onSave } = renderGrid()
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    await user.click(screen.getByRole('switch', { name: 'Show Alpha' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(shownOrder()).toEqual(['Alpha', 'Bravo', 'Charlie'])
    expect(onSave).not.toHaveBeenCalled()
  })

  it('reset to default shows the default and saves no layout of the user own', async () => {
    const { user, onSave } = renderGrid({
      layout: { order: ['charlie', 'bravo', 'alpha'], hidden: ['bravo'] },
      defaultLayout: { order: ['bravo', 'alpha', 'charlie'], hidden: [] },
    })
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    await user.click(screen.getByRole('button', { name: 'Reset to default' }))
    expect(shownOrder()).toEqual(['Bravo', 'Alpha', 'Charlie'])
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith(null)
  })

  it('lets an admin save the arrangement as the unit default', async () => {
    const { user, onSaveDefault, onSave } = renderGrid({ canSetDefault: true })
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    await user.click(screen.getByRole('switch', { name: 'Show Charlie' }))
    await user.click(screen.getByRole('button', { name: 'Save as unit default' }))
    expect(onSaveDefault).toHaveBeenCalledWith({ order: ['alpha', 'bravo', 'charlie'], hidden: ['charlie'] })
    expect(onSave).not.toHaveBeenCalled()
  })

  it('offers no unit default to other users', async () => {
    const { user } = renderGrid()
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    expect(screen.queryByRole('button', { name: 'Save as unit default' })).toBeNull()
  })

  it('stays in edit mode when the save fails', async () => {
    const { user } = renderGrid({ onSave: vi.fn().mockRejectedValue(new Error('nope')) })
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('button', { name: 'Cancel' })).toBeEnabled()
  })

  it('keeps tile content out of reach while editing', async () => {
    const { user } = renderGrid()
    await user.click(screen.getByRole('button', { name: 'Edit layout' }))
    const cell = screen.getByRole('region', { name: 'Alpha' }).closest('[data-tile-id]')
    expect(within(cell).getByRole('button', { name: 'Move Alpha' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Alpha' }).parentElement).toHaveAttribute('inert')
  })
})
