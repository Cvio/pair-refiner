# 1. Temperature and reasoning effort

Date: 2026-10-18. Decided with the user during M1.

## Why

BUILD.md says "Temperature 0 for every call". OpenRouter's model list (checked 2026-10-18) shows
that no current Anthropic or OpenAI model accepts `temperature` (it is missing from their
`supported_parameters`). Gemini, DeepSeek and Meta models do accept it.

Most top models also have mandatory reasoning (`reasoning.mandatory: true`): they always think
before answering. The thinking is billed as output tokens, and how much they think depends on the
effort level.

## Decision

- **Temperature:** send `temperature: 0` to every model whose `supported_parameters` include
  `temperature`; leave it out for the rest. Repeatability comes from the cache: every answer is
  stored, so a re-run reuses it. The cache key includes the settings actually sent, so it records
  whether temperature was sent.
- **Reasoning effort:** use the lowest effort each model offers, from its
  `reasoning.supported_efforts`, in this order: `none`, `minimal`, `low`, `medium`, `high`,
  `xhigh`, `max`. Models with no `reasoning` entry get no reasoning setting. The effort is a run
  setting, so the M6 test run can check whether more effort helps.
