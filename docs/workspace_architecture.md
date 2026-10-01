# Collaborative project files

Each project owns a directory named with its project UUID under `WORKSPACE_ROOT`. This
directory is initialized as a Git repository when the project is created. Older projects
get a directory the first time their file API is opened. The name comes from the server's
database ID, not from a user supplied path. The API rejects path traversal, hidden paths,
symlinks escaping the workspace, and files over 1 MB. It enforces project and organization
authorization on every file and Git operation.

## Live editing stack

- **Next.js + CodeMirror 6** provides the browser code and text editor.
- **Yjs** merges simultaneous text edits. Its awareness state gives users live presence and
  colored cursors. The editor binding is `y-codemirror.next`.
- **Hocuspocus** relays Yjs updates over WebSockets. It verifies the user's bearer token and
  project edit permission through FastAPI before admitting a connection, then rechecks while
  edits continue. It writes both the UTF-8 file and a Yjs state snapshot on the shared volume.
  Direct edits to a file on that volume are brought into an open live document on a short poll.
- **FastAPI + PostgreSQL** holds project and permission data and exposes the file browser,
  checkpoint history, Git remote setting and push operations.
- **Planner agent** uses the developer's `DEFAULT_GEMINI_API_KEY` on FastAPI. Project creation asks Gemini for an initial task breakdown. If the key or provider is unavailable, the project still opens and the task board offers a retry after configuration.
- **Assigned agents** use OpenAI, Anthropic, Gemini, or an OpenAI-compatible API with each user's browser-stored API key, or the shared default Gemini agent through FastAPI. The default key never reaches the browser. Task assignment in the browser asks the planner to choose files, sends a bounded file snapshot to the worker model, and applies its returned file contents through Yjs. The board polls task progress every three seconds and moves completed edits to review. The browser tab must stay open while a task runs; there is no durable background worker for user keys.
- **Git** records the folder history. Users can commit a named checkpoint on demand. The
  backend commits changed folders every five minutes. Push uses an HTTPS personal access
  token once, passed to Git through `GIT_ASKPASS` and never saved in Git config or the database.

The API and collaboration service must use the **same persistent POSIX directory**. Locally,
the default is `./var/workspaces`. On one AWS host, mount an EBS volume and set
`WORKSPACE_HOST_PATH` for Docker Compose; for multiple hosts, use an EFS access point with
the same UID (10001) for both containers. Provision and chown the host directory to UID
10001 before starting the containers. EBS is tied to one host; EFS is needed when the API
and collaboration service run on different hosts. The WebSocket endpoint must be exposed
through WSS under the same access controls as the web app.

Set `PUBLIC_WEB_URL=https://app.example.com`, `PUBLIC_API_URL=https://api.example.com` and
`PUBLIC_COLLAB_URL=wss://collab.example.com` before building the frontend image. Set
`SECRET_KEY` (a unique value of at least 32 characters) and `DB_PASSWORD` for production.
The Git remote must be HTTPS
and its host must be in `GIT_ALLOWED_HOSTS`; the default list is GitHub, GitLab and
Bitbucket. Use a Git token with write access to the target repository. No Git token is
needed for local editing and checkpoints.

This is a collaborative **text file** workspace. It does not run arbitrary code returned by
agents. Very large files and binary assets require a separate artifact flow. A single
Hocuspocus instance should own a workspace's live documents; a multi-instance deployment
needs shared Yjs messaging before scaling the collaboration service horizontally.
