# MIA-LABS
🧪 AI agents debating, repairing, mutating and evolving symbolic equations. Built from scratch in Python with persistent memory and local LLM support.
# 🧪 MIA — Multi-Agent Intelligence Alchemy

> Autonomous symbolic discovery through AI collaboration, memory, validation, repair, and evolution.

MIA is an experimental multi-agent research framework built entirely in Python.

Instead of relying on a single AI model to generate ideas, MIA creates a collaborative ecosystem of specialized AI agents that generate, debate, validate, repair, mutate, and archive symbolic equations.

Each agent has a role.
Each equation has a history.
Each discovery becomes part of a growing memory.

---

## 🚀 What is MIA?

MIA explores a simple question:

> What happens when multiple AI agents collaborate, criticize each other, remember past discoveries, and continuously improve symbolic knowledge?

To answer this, MIA orchestrates a network of agents that work together to build and refine equations under semantic, causal, and dimensional constraints.

The result is a system capable of:

- Generating new variables
- Creating symbolic equations
- Validating consistency
- Repairing failures
- Mutating promising candidates
- Tracking equation lineages
- Building long-term memory

---

## 🧠 Core Concepts

### Multi-Agent Collaboration

Every equation passes through multiple perspectives.

Some agents create.

Some agents challenge.

Some agents repair.

Some agents archive.

The goal is not to generate equations quickly.

The goal is to generate equations that survive criticism.

---

### Persistent Memory

MIA remembers.

The system stores:

- Validated equations
- Rejected equations
- Variables
- Definitions
- Causal roles
- Validation reports
- Symbolic relationships
- Session knowledge

This allows future generations to build upon previous discoveries rather than starting from scratch.

---

### Equation Evolution

Equations are treated as evolving entities.

They can:

- Be approved
- Be rejected
- Be repaired
- Be mutated
- Produce descendants
- Form lineages

MIA tracks the complete ancestry of symbolic discoveries.

---

## ⚙️ Main Features

### 🧠 AI Debate System

Multiple agents discuss and evaluate candidate equations.

### 📚 Persistent Knowledge Memory

Knowledge survives across sessions.

### 🔧 Automatic Repair Engine

Rejected equations can be repaired automatically.

### 🧬 Mutation Engine

Promising equations generate new variants.

### 🌳 Lineage Tracking

Track the evolution of equations over time.

### 📏 Dimensional Validation

Verify unit consistency.

### 🔗 Causal Validation

Verify logical relationships between variables.

### 🖥️ Interactive GUI

Monitor and control the entire process through a dedicated interface.

### 🏠 Fully Local

Runs with local LLMs through Ollama.

No cloud services required.

---

## 🤖 Agents

MIA includes multiple specialized agents.

Examples include:

| Agent | Role |
|---------|---------|
| Aurelius | Equation generation |
| Basilide | Alternative reasoning |
| HermesValidator | Semantic validation |
| Chymicus | Equation repair |
| Sentinelle | Consistency checks |
| Archiviste | Memory and archival |
| Synthétiseur | Knowledge synthesis |
| VariableValidator | Variable verification |
| EquationValidator | Equation validation |
| FinalValidator | Final approval |

Each agent may use a different language model.

---

## 🔄 Discovery Workflow

```text
Variable Generation
          ↓
Equation Generation
          ↓
Validation
          ↓
 ┌────────┴────────┐
 │                 │
Approved       Rejected
 │                 │
 ↓                 ↓
Archive         Repair
 │                 │
 ↓                 ↓
Mutation ←─────────┘
 │
 ↓
New Generation
```

The cycle continues as long as the experiment runs.

---

## 🤖 Model Support

MIA works with local Ollama models.

Examples:

- Gemma 2
- Gemma 3
- Qwen
- Llama
- Mistral
- Any Ollama-compatible model

Each agent can be configured independently through `config.py`.

Example:

```python
self.model_aurelius = "gemma2:2b"
self.model_hermes = "qwen3:4b"
self.model_archiviste = "llama3.2:3b"
```

Run lightweight models on CPU or larger models on GPU.

---

## 🖥️ Requirements

- Python 3.x
- Ollama
- Local language model

Minimum tested configuration:

- Gemma2:2b
- CPU only

Slower, but fully functional.

---

## 🚀 Quick Start

Clone the repository:

```bash
git clone https://github.com/yourname/mia.git
cd mia
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install a model:

```bash
ollama pull gemma2:2b
```

Launch MIA:

```bash
python ui_launcher.py
```

---

## 📊 Project Status

MIA is an active experimental project.

Current capabilities include:

- Multi-agent orchestration
- Persistent memory
- Equation generation
- Equation validation
- Repair engine
- Mutation engine
- Lineage tracking
- Session management
- Local LLM support

---

## ⚠️ Disclaimer

MIA is a research and experimentation platform.

Generated equations should not be interpreted as scientific truths without independent verification and experimental validation.

The purpose of the project is to explore autonomous symbolic discovery and collaborative AI reasoning.

---

## 🛠️ Built With

- Python
- Ollama
- Local LLMs
- Persistent memory systems
- Multi-agent orchestration
- A lot of experimentation

---

## 📜 License

MIT License

---

# 🧪 MIA

**Multi-Agent Intelligence Alchemy**

*Where equations evolve through debate.*
