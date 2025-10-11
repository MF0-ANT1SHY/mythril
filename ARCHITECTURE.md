# Mythril Architecture Overview

This document provides a high-level overview of Mythril's architecture. For a comprehensive analysis, see [docs/source/architecture-analysis.rst](docs/source/architecture-analysis.rst).

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Entry Point                          │
│                  (mythril/interfaces/cli.py)                    │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │   analyze    │  │  disassemble │  │   concolic       │     │
│  │   command    │  │   command    │  │   command        │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────────┘     │
│         │                 │                  │                 │
└─────────┼─────────────────┼──────────────────┼─────────────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core Analysis Engine                         │
│           (MythrilAnalyzer, MythrilDisassembler)                │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              Symbolic Execution Engine                  │    │
│  │                  (Laser EVM)                           │    │
│  │                                                         │    │
│  │  ┌──────────────────────────────────────────────┐     │    │
│  │  │         Detection Module System              │     │    │
│  │  │                                              │     │    │
│  │  │  ┌────────────┐  ┌────────────────────┐    │     │    │
│  │  │  │ Built-in   │  │  Plugin System     │    │     │    │
│  │  │  │ Modules    │  │  (Entry Points)    │    │     │    │
│  │  │  │            │  │                    │    │     │    │
│  │  │  │ • EtherThief    │ • Custom        │    │     │    │
│  │  │  │ • Integer  │  │   Detection       │    │     │    │
│  │  │  │ • Delegate │  │   Modules         │    │     │    │
│  │  │  │ • ... (17) │  │ • Laser Plugins   │    │     │    │
│  │  │  └────────────┘  └────────────────────┘    │     │    │
│  │  └──────────────────────────────────────────────┘     │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Patterns

### 1. **Single Entry Point with Command Dispatching**
- `mythril/__main__.py` → `mythril/interfaces/cli.py:main()`
- Uses `argparse` subparsers for command routing
- Shared parent parsers for common options

### 2. **Singleton Pattern for Global Registries**
- `ModuleLoader`: Manages detection modules
- `MythrilPluginLoader`: Manages plugins
- `PluginDiscovery`: Discovers installed plugins

### 3. **Plugin Architecture via Entry Points**
- Built-in modules: 17 detection modules
- External plugins: Loaded via `setuptools` entry points
- Type-based dispatch: Detection modules vs. Laser plugins

### 4. **Abstract Base Classes for Extensibility**
- `DetectionModule`: Base for all security detectors
- `MythrilPlugin`: Base for all plugins
- Hook system: Pre/post hooks for EVM instructions

### 5. **Format-Agnostic Output**
- Supports JSON, text, markdown formats
- Error handling respects output format
- Report abstraction layer

## Quick Reference

### Adding a New Detection Module

```python
from mythril.analysis.module import DetectionModule, EntryPoint
from mythril.analysis.report import Issue

class MyDetector(DetectionModule):
    name = "My Detector"
    swc_id = "SWC-XXX"
    description = "Detects specific vulnerability"
    entry_point = EntryPoint.CALLBACK
    post_hooks = ["SSTORE"]  # EVM opcode to hook
    
    def _execute(self, state):
        # Detection logic
        if self._is_vulnerable(state):
            return [Issue(...)]
        return []
```

### Creating an External Plugin

**1. Create plugin class:**
```python
from mythril.analysis.module import DetectionModule

class ExternalDetector(DetectionModule):
    name = "External Detector"
    plugin_default_enabled = False  # Don't auto-load
    # ... implementation
```

**2. Register in setup.py:**
```python
setup(
    name="mythril-external-detector",
    entry_points={
        "mythril.plugins": [
            "external_detector = my_package:ExternalDetector"
        ]
    }
)
```

**3. Install and use:**
```bash
pip install mythril-external-detector
myth analyze contract.sol
```

## Module Loading Flow

```
1. CLI starts → MythrilPluginLoader() singleton created
   ↓
2. MythrilPluginLoader.__init__()
   ↓
3. _load_default_enabled()
   ↓
4. PluginDiscovery.get_plugins(default_enabled=True)
   ↓
5. For each plugin:
   - PluginDiscovery.build_plugin()
   - MythrilPluginLoader.load()
   - Type dispatch: DetectionModule → ModuleLoader.register_module()
                   MythrilLaserPlugin → LaserPluginLoader.load()
   ↓
6. Built-in modules loaded in ModuleLoader.__init__()
   ↓
7. Analysis executes with all registered modules
```

## Error Handling Strategy

```python
# Custom exception hierarchy
MythrilBaseException
├── CriticalError
├── DetectorNotFoundError
├── CompilerError
└── ... (others)

# Format-aware error output
def exit_with_error(format, message):
    if format == "json":
        print(json.dumps({"error": message}))
    else:
        log.error(message)
    sys.exit(1)
```

## Testing Hooks

- **Module Reset**: `DetectionModule.reset_module()` for test isolation
- **Dependency Injection**: All major components accept dependencies via constructor
- **Mock-Friendly**: Abstract interfaces enable easy mocking
- **Singleton Reset**: Test can clear singleton state via `_instances` dict

## Performance Optimizations

1. **Lazy Loading**: Heavy components loaded only when needed
2. **Singleton Pattern**: Avoid duplicate object creation
3. **Module Caching**: Detection modules cache analyzed code locations
4. **Entry Point Caching**: Plugin discovery cached in PluginDiscovery

## File Structure Reference

```
mythril/
├── __main__.py              # Entry point
├── interfaces/
│   └── cli.py              # CLI orchestration (~975 lines)
├── plugin/
│   ├── interface.py        # Plugin base classes
│   ├── loader.py           # Plugin loader (singleton)
│   └── discovery.py        # Entry point discovery
├── analysis/
│   └── module/
│       ├── base.py         # DetectionModule ABC
│       ├── loader.py       # Module loader (singleton)
│       └── modules/        # 17 built-in detectors
├── laser/                  # Symbolic execution engine
├── mythril/               # Core analysis logic
└── exceptions.py          # Exception hierarchy
```

## Core Components

| Component | Purpose | Pattern |
|-----------|---------|---------|
| `cli.py` | Command dispatcher | Command pattern |
| `ModuleLoader` | Module registry | Singleton, Registry |
| `MythrilPluginLoader` | Plugin loader | Singleton, Factory |
| `PluginDiscovery` | Plugin discovery | Singleton, Lazy loading |
| `DetectionModule` | Module interface | Template method, ABC |
| `MythrilAnalyzer` | Analysis orchestration | Facade |

## Reusable Techniques

1. ✅ **Entry points for plugin discovery**
2. ✅ **Singleton metaclass pattern**
3. ✅ **Abstract base classes with hooks**
4. ✅ **Argparse parent parsers**
5. ✅ **Type-based dispatch**
6. ✅ **Lazy property loading**
7. ✅ **Format-agnostic output**
8. ✅ **Custom exception hierarchies**
9. ✅ **Dependency injection**
10. ✅ **Hook-based extensibility**

## Further Reading

- **Full Architecture Analysis**: [docs/source/architecture-analysis.rst](docs/source/architecture-analysis.rst)
- **Detection Modules**: [docs/source/analysis-modules.rst](docs/source/analysis-modules.rst)
- **Creating Modules**: [docs/source/create-module.rst](docs/source/create-module.rst)

---

**Last Updated**: 2025-10-11
