import { describe, it, expect } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { renderWithProviders } from '@/test/render'
import DocumentStoragePage from './DocumentStoragePage'

// Mount endpoints (Promise.all in mount effect):
//   GET /folders     (array; loadFolders, toast.error on failure)
//   GET /documents   (array; loadAllDocuments, .catch -> [])
// Selecting a folder -> GET /folders/:id/documents. With no folder selected the
// "Document Storage" prompt shows. Folder navigation is the central interaction.

const FOLDERS = [
  { id: 1, name: 'Certifications', parent_id: null, document_count: 2, is_system: false },
  { id: 2, name: 'Insurance', parent_id: null, document_count: 0, is_system: false },
]

const FOLDER1_DOCS = [
  { id: 11, title: 'Part 107.pdf', filename: 'part107.pdf', mime_type: 'application/pdf', file_size_bytes: 51200, uploaded_at: '2026-06-01', folder_id: 1 },
]

function mockMount(overrides = {}) {
  const base = {
    folders: () => HttpResponse.json(FOLDERS),
    documents: () => HttpResponse.json([]),
    folderDocs: () => HttpResponse.json(FOLDER1_DOCS),
    ...overrides,
  }
  server.use(
    http.get('/api/folders', base.folders),
    http.get('/api/documents', base.documents),
    http.get('/api/folders/:id/documents', base.folderDocs),
  )
}

describe('DocumentStoragePage', () => {
  it('renders without crashing', async () => {
    mockMount()
    renderWithProviders(<DocumentStoragePage />, { role: 'admin' })
    expect(await screen.findByText('Folders')).toBeInTheDocument()
  })

  it('renders the folder tree and the no-folder-selected prompt', async () => {
    mockMount()
    renderWithProviders(<DocumentStoragePage />, { role: 'admin' })
    expect(await screen.findByText('Certifications')).toBeInTheDocument()
    expect(screen.getByText('Insurance')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Document Storage' })).toBeInTheDocument()
  })

  it('renders chrome with an empty folder list', async () => {
    mockMount({ folders: () => HttpResponse.json([]) })
    renderWithProviders(<DocumentStoragePage />, { role: 'admin' })
    expect(await screen.findByText('Folders')).toBeInTheDocument()
    expect(screen.getByText('Unfiled')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Document Storage' })).toBeInTheDocument()
  })

  it('renders chrome when /folders 500s (loading clears, prompt shows)', async () => {
    mockMount({ folders: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderWithProviders(<DocumentStoragePage />, { role: 'admin' })
    expect(await screen.findByRole('heading', { name: 'Document Storage' })).toBeInTheDocument()
  })

  it('loads a folder\'s documents when the folder is clicked', async () => {
    let requestedFolder = null
    mockMount({
      folderDocs: ({ params }) => { requestedFolder = params.id; return HttpResponse.json(FOLDER1_DOCS) },
    })
    const { user } = renderWithProviders(<DocumentStoragePage />, { role: 'admin' })
    await screen.findByText('Certifications')

    await user.click(screen.getByText('Certifications'))
    expect(await screen.findByText('Part 107.pdf')).toBeInTheDocument()
    expect(requestedFolder).toBe('1')
  })

  it('shows the per-folder empty state for a folder with no documents', async () => {
    mockMount({ folderDocs: () => HttpResponse.json([]) })
    const { user } = renderWithProviders(<DocumentStoragePage />, { role: 'admin' })
    await screen.findByText('Insurance')

    await user.click(screen.getByText('Insurance'))
    expect(await screen.findByText('No documents in this folder yet.')).toBeInTheDocument()
  })

  it('opens the upload panel targeting the selected folder', async () => {
    mockMount()
    const { user } = renderWithProviders(<DocumentStoragePage />, { role: 'admin' })
    await screen.findByText('Certifications')

    await user.click(screen.getByText('Certifications'))
    await screen.findByText('Part 107.pdf')
    await user.click(screen.getByRole('button', { name: /Upload/ }))

    const target = await screen.findByText(/Uploading to:/)
    expect(target).toHaveTextContent('Uploading to: Certifications')
    expect(screen.getByText('Choose file...')).toBeInTheDocument()
  })

  it('uploads a general document with no folder selected (lands in Unfiled)', async () => {
    let uploadedForm = null
    mockMount()
    server.use(http.post('/api/documents/upload', async ({ request }) => {
      uploadedForm = await request.formData()
      return HttpResponse.json({ id: 99 })
    }))
    const { user } = renderWithProviders(<DocumentStoragePage />, { role: 'admin' })
    await screen.findByText('Certifications')

    await user.click(screen.getByRole('button', { name: /Upload/ }))
    const input = document.querySelector('input[type="file"]')
    const file = new File(['hello'], 'faa-auth.pdf', { type: 'application/pdf' })
    await user.upload(input, file)
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(uploadedForm).not.toBeNull())
    expect(uploadedForm.get('entity_type')).toBe('general')
    expect(uploadedForm.get('entity_id')).toBeNull()
    expect(uploadedForm.get('folder_id')).toBeNull()
  })

  it('hides the upload button for a viewer', async () => {
    server.use(http.get('/api/auth/me', () =>
      HttpResponse.json({ id: 1, username: 'v', display_name: 'v', role: 'viewer' })))
    mockMount()
    renderWithProviders(<DocumentStoragePage />, { role: 'viewer' })
    await screen.findByText('Certifications')
    expect(screen.queryByRole('button', { name: /Upload/ })).toBeNull()
  })

  // The folder list is a tree: nodes are selectable, they expand, and each one
  // carries its own rename and delete controls. It was marked up as a button,
  // which describes none of that and put real buttons inside a button.
  describe('the folder list is exposed as a tree', () => {
    it('names the tree and its items', async () => {
      mockMount()
      renderWithProviders(<DocumentStoragePage />, { role: 'admin' })

      await screen.findByText('Certifications')
      const tree = screen.getByRole('tree', { name: 'Document folders' })
      // Two folders plus Unfiled.
      expect(within(tree).getAllByRole('treeitem')).toHaveLength(3)
    })

    it('marks the selected folder as selected', async () => {
      mockMount()
      const { user } = renderWithProviders(<DocumentStoragePage />, { role: 'admin' })

      await user.click(await screen.findByText('Certifications'))

      const selected = screen.getAllByRole('treeitem').filter(n => n.getAttribute('aria-selected') === 'true')
      expect(selected).toHaveLength(1)
      expect(selected[0]).toHaveTextContent('Certifications')
    })

    it('does not claim a childless folder is collapsed', async () => {
      // aria-expanded on a leaf tells a screen reader there is something to
      // open. Only a node with children carries it, and none of these have any.
      mockMount()
      renderWithProviders(<DocumentStoragePage />, { role: 'admin' })

      await screen.findByText('Certifications')
      for (const node of screen.getAllByRole('treeitem')) {
        expect(node).not.toHaveAttribute('aria-expanded')
      }
    })

    it('marks a folder with children as expandable, and tracks its state', async () => {
      // Folders load expanded, so the attribute starts true and the click
      // collapses rather than opens.
      mockMount({ folders: () => HttpResponse.json([
        ...FOLDERS,
        { id: 3, name: 'Part 107', parent_id: 1, document_count: 1, is_system: false },
      ]) })
      const { user } = renderWithProviders(<DocumentStoragePage />, { role: 'admin' })

      await screen.findAllByText('Certifications')
      const parent = screen.getAllByRole('treeitem')
        .find(n => n.textContent.includes('Certifications'))
      expect(parent).toHaveAttribute('aria-expanded', 'true')
      expect(within(screen.getByRole('group')).getByRole('treeitem')).toHaveTextContent('Part 107')

      await user.click(parent)

      expect(parent).toHaveAttribute('aria-expanded', 'false')
      expect(screen.queryByRole('group')).toBeNull()
    })
  })
})
