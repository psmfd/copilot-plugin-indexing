# Copilot Indexing

Proof of concept for local CocoIndex Code search in GitHub Copilot CLI and the
Copilot harness in VS Code Chat. The companion plugin registers
`search_codebase` through the Copilot extension runtime and invokes the
`ccc` command-line interface. Search results are visible as tool output.
Install it on its own or alongside `agent-framework-copilot`. The indexing
plugin has its own setup and requires no framework files. Both installations
use the same tool name. Framework agents with explicit tool allowlists can use
it when their profile includes `search_codebase`.

## Set up CocoIndex

Clone the plugin and run its setup script as your own user with Python 3.11 or
newer on macOS or Linux.

```sh
git clone https://github.com/psmfd/copilot-plugin-indexing.git
cd copilot-plugin-indexing
/bin/bash ./setup.sh --workspace /path/to/checkout
```

To select a particular Python interpreter, invoke it directly, for example
`python3.13 ./setup.py --workspace /path/to/checkout`.

Setup installs `cocoindex-code[full]==0.2.35` into an isolated virtual
environment. To reuse a compatible pipx or virtual environment installation on
first setup, add `--ccc /absolute/path/to/ccc`. Subsequent runs reuse the
recorded interpreter. If that installation moved, rerun with `--ccc` pointing
to the new location.

Setup prepares the pinned Snowflake embedding model from the local Hugging
Face cache or downloads the required files on first use. It verifies the weights
and stores the model, executable location, engine configuration, and indexes
under `~/.config/copilot-indexing`. Set the same absolute
`COPILOT_INDEXING_HOME` in both clients and during setup if you need another
location. The default location works when VS Code is launched from the desktop.
The runtime uses local embeddings and requires no embedding API key.
The host must allow CocoIndex's local daemon to bind a Unix socket.

Pass the root of each Git checkout you want to index. If CocoIndex project
settings are absent, `ccc init` creates them and updates the checkout's
`.gitignore`. Setup preserves existing project settings and keeps its index
databases separate from existing Pi indexes. Run the same command again for an
incremental refresh. Both clients use the same index for the same checkout on
the same host. Automatic refresh is outside this prototype.

### Set up or refresh from VS Code

To run setup from VS Code without adding a task to each checkout, open the
Command Palette and choose **Tasks: Open User Tasks**. Add this object to the
`tasks` array, replacing the script path with the absolute path to your copy of
this plugin:

```json
{
  "label": "Copilot Indexing: Set Up / Refresh",
  "type": "process",
  "command": "/bin/bash",
  "args": [
    "/absolute/path/to/copilot-plugin-indexing/setup.sh",
    "--workspace",
    "${workspaceFolder}"
  ],
  "problemMatcher": [],
  "presentation": {
    "reveal": "always",
    "panel": "dedicated"
  }
}
```

Open the Git checkout root as a single-folder workspace, then choose
**Tasks: Run Task** and select **Copilot Indexing: Set Up / Refresh**. The first
run prepares the toolchain and index; later runs incrementally refresh it. The
task shows setup output and errors in the terminal. For a multi-root workspace,
open the desired checkout root separately so the task has an unambiguous
workspace folder.

The first run may download dependencies and model files and may create
`.cocoindex_code` and update the checkout's `.gitignore`, as described above.
If you use `COPILOT_INDEXING_HOME`, make sure VS Code and this task use the same
absolute value. This task does not install the plugin in VS Code or refresh the
index automatically.

## Load the plugin

- **Copilot CLI 1.0.114** — launch in the prepared checkout with
  `copilot --experimental --disable-builtin-mcps --plugin-dir /path/to/copilot-plugin-indexing`.
  Approve the indexing extension when prompted. The package can also be
  installed from a local path with `copilot plugin install` on this version.
- **VS Code 1.148.0** — open the prepared checkout, select the **Copilot**
  harness in Chat, and run **Chat: Install Plugin from Source** with the
  plugin directory. Enable `chat.canvases.enabled` in user settings. In this
  VS Code build, that setting enables the runtime extension surface used by
  the indexing tool. Start a fresh session and approve the extension if
  prompted. [VS Code Canvases setting](https://code.visualstudio.com/docs/agents/run/canvases)

For a session with MCP disabled, use a separate `COPILOT_HOME` without user
MCP servers and a checkout without workspace MCP configuration. In the VS Code
profile, set `chat.mcp.access` to `none` and
`chat.agentHost.githubMcpServer.enabled` to `false`. Set
`"disabledMcpServers": ["github-mcp-server"]` in the isolated Copilot home's
`settings.json` as well. Check the **Agent Host** output for the built-in
server's `disabled (stopped)` status. Search runs through the native
`search_codebase` extension and the CocoIndex CLI.

## Qualify the integration

1. Use a disposable checkout with a function or document containing a distinctive
   description. Run workspace setup once.
2. In each client, ask it to use `search_codebase` to find the content by
   meaning. Inspect the tool call and confirm a relative path and line number
   from the fixture. Run once with indexing alone and once with both plugins
   enabled. With just the framework enabled, confirm the tool is absent.
3. When testing both plugins, add `search_codebase` to the explicit `tools`
   allowlist of a disposable custom agent. Rerun the query through that agent,
   then confirm the tool is absent for an agent whose allowlist omits it.
4. Edit the fixture, rerun workspace setup to refresh the index, and verify the
   updated content appears in a search from the other client.

Copilot CLI 1.0.114 and VS Code Chat 1.148.0 returned indexed snippets with
relative paths and line ranges both standalone and with a framework package
built from `dev` at `4dd008e`. The CLI also returned a snippet through a
custom agent that explicitly allowed the tool. The CLI controls that omitted
the tool or loaded only the framework made no indexing calls. VS Code 1.147.0
was tested through its bundled Copilot runtime (1.0.111-0).

Setup reused an existing CocoIndex 0.2.35 installation and separately built
an index after installing the pinned engine into a fresh Python 3.13.14
environment. Both runs used the pinned model from the local cache.

After a fixture edit, search still returned the original snippet until setup
reprocessed the changed file. Both clients returned the updated snippet from
the shared index, with and without the framework installed. The refresh is
manual and uses the same setup command as the initial build.
