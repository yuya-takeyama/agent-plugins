# grasp

Agents can now produce explainers faster than people can understand them,
and polished material makes learners feel they understood when they did not.
grasp makes an agent plan what the learner will be able to do unaided, and
where the learner does the thinking, before any content is written. It also
reviews existing drafts against the same evidence.

| Skill | Output |
| --- | --- |
| learning-design | A learning brief (learner, objectives, misconceptions, sequence, thinking points, aligned checks) or a rubric review of a draft |

The skill does not render anything. Pair it with a format skill such as
[YES](../yes/README.md): write the brief with `grasp:learning-design`, then
build the article, slides, video, quiz, or course from it, then review the
result with the rubric.

The evidence base (multimedia learning, cognitive load, retrieval and spacing,
productive failure, refutation, feedback, fluency illusions, and recent
studies on AI assistance and skill formation) is in
[principles.md](skills/learning-design/references/principles.md) with sources.

## Installation

### Claude Code

```text
/plugin marketplace add yuya-takeyama/agent-plugins
/plugin install grasp@yuya-plugins
```

Use `/grasp:learning-design`, or ask for an explainer, course, or review of
teaching material and let the agent pick it up.

### Codex

```sh
codex plugin marketplace add yuya-takeyama/agent-plugins
```

Install `grasp` from the `yuya-plugins` source in the plugin browser, then
start a new session.

## License

[MIT](LICENSE). Cited studies belong to their authors; the skill summarizes
them and links to the originals.
