import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataTable } from './DataTable'

const columns = [
  { key: 'name', label: 'Name', sortable: true },
  { key: 'role', label: 'Role' },
]
const data = [
  { id: 1, name: 'Ada', role: 'pilot' },
  { id: 2, name: 'Ben', role: 'admin' },
]

describe('DataTable', () => {
  it('renders column headers and row data', () => {
    render(<DataTable columns={columns} data={data} />)
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Role')).toBeInTheDocument()
    expect(screen.getByText('Ada')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
  })

  it('shows the empty state when data is empty', () => {
    render(<DataTable columns={columns} data={[]} />)
    expect(screen.getByText('No data available')).toBeInTheDocument()
  })

  it('calls onSort with the column key when a sortable header is clicked', async () => {
    const user = userEvent.setup()
    const onSort = vi.fn()
    render(<DataTable columns={columns} data={data} onSort={onSort} />)
    await user.click(screen.getByRole('button', { name: /Name/ }))
    expect(onSort).toHaveBeenCalledWith('name')
  })

  it('does not render a sort button for non-sortable columns', () => {
    render(<DataTable columns={columns} data={data} />)
    // 'Role' is not sortable, so it is not a button.
    expect(screen.queryByRole('button', { name: /Role/ })).not.toBeInTheDocument()
  })

  it('reflects sort direction via aria-sort on the active column', () => {
    render(<DataTable columns={columns} data={data} sortKey="name" sortDir="asc" />)
    const nameHeader = screen.getByText('Name').closest('th')
    expect(nameHeader).toHaveAttribute('aria-sort', 'ascending')
  })

  it('uses the column render callback for custom cells', () => {
    const cols = [
      { key: 'name', label: 'Name' },
      { key: 'role', label: 'Role', render: (val) => <span data-testid="custom">{val.toUpperCase()}</span> },
    ]
    render(<DataTable columns={cols} data={data} />)
    const custom = screen.getAllByTestId('custom')
    expect(custom[0]).toHaveTextContent('PILOT')
  })

  it('renders pagination and fires onPageChange when totalPages > 1', async () => {
    const user = userEvent.setup()
    const onPageChange = vi.fn()
    render(
      <DataTable columns={columns} data={data} page={2} totalPages={3} onPageChange={onPageChange} />,
    )
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next page' }))
    expect(onPageChange).toHaveBeenCalledWith(3)
    await user.click(screen.getByRole('button', { name: 'Previous page' }))
    expect(onPageChange).toHaveBeenCalledWith(1)
  })

  it('renders skeleton rows while loading', () => {
    const { container } = render(<DataTable columns={columns} data={[]} loading />)
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0)
    expect(screen.queryByText('No data available')).not.toBeInTheDocument()
  })
})
