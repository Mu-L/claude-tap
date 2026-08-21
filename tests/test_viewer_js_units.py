from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for viewer JS unit tests")
def test_viewer_split_js_core_units_run_without_playwright() -> None:
    script = textwrap.dedent(
        r"""
        const assert = require('assert/strict');
        const fs = require('fs');
        const path = require('path');
        const vm = require('vm');

        const repoRoot = process.argv.at(-1);
        const assetDir = path.join(repoRoot, 'claude_tap', 'viewer_assets');

        function classList() {
          return { add() {}, remove() {}, toggle() {}, contains() { return false; } };
        }

        function element() {
          return {
            style: {},
            dataset: {},
            classList: classList(),
            children: [],
            innerHTML: '',
            textContent: '',
            value: '',
            setAttribute() {},
            appendChild(child) { this.children.push(child); return child; },
            removeChild(child) { this.children = this.children.filter(item => item !== child); },
            addEventListener() {},
            querySelector() { return null; },
            querySelectorAll() { return []; },
            focus() {},
            select() {},
            setSelectionRange() {},
            remove() {},
          };
        }

        const context = {
          console,
          URLSearchParams,
          setTimeout() {},
          clearTimeout() {},
          requestAnimationFrame(callback) { if (typeof callback === 'function') callback(); return 1; },
          cancelAnimationFrame() {},
          window: {
            location: { search: '?embed=1&hideHeader=1&density=compact&theme=dark' },
            localStorage: { getItem() { return null; }, setItem() {} },
            matchMedia() { return { matches: false }; },
          },
          navigator: { language: 'en', clipboard: null },
          document: {
            documentElement: { dataset: {}, classList: classList() },
            body: element(),
            querySelector() { return element(); },
            querySelectorAll() { return []; },
            getElementById() { return element(); },
            createElement() { return element(); },
            addEventListener() {},
            removeEventListener() {},
            execCommand() { return false; },
          },
        };
        vm.createContext(context);

        for (const assetName of [
          'state.js',
          'responses.js',
          'lazy_loading.js',
          'i18n_ui.js',
          'live_bootstrap.js',
          'filters_search.js',
          'renderers.js',
          'diff.js',
          'utilities_mobile.js',
        ]) {
          const source = fs.readFileSync(path.join(assetDir, assetName), 'utf8');
          vm.runInContext(source, context, { filename: assetName });
        }

        const plain = value => JSON.parse(JSON.stringify(value));

        assert.deepEqual(plain(context.parseEmbedQueryOptions()), {
          enabled: true,
          hideHeader: true,
          hidePath: false,
          hideHistory: false,
          hideControls: false,
          compact: true,
          theme: 'dark',
        });

        assert.deepEqual(plain(context.turnSortSegments('1.02.beta')), [1, 2, 0]);
        assert.equal(context.compareTurns('1.10', '1.2') > 0, true);
        assert.equal(context.compareTurns('2', '10') < 0, true);

        assert.deepEqual(
          plain(context.lineDiff('alpha\nold\nsame', 'alpha\nnew\nsame')),
          [
            { type: 'ctx', text: 'alpha' },
            { type: 'change', oldText: 'old', newText: 'new' },
            { type: 'ctx', text: 'same' },
          ],
        );

        const events = [
          { event: 'response.created', data: { response: { id: 'resp_first' } } },
          {
            event: 'response.output_item.done',
            data: {
              output_index: 0,
              item: {
                id: 'item_first_tool',
                type: 'function_call',
                call_id: 'call_1',
                name: 'shell',
                arguments: '{"cmd":"pwd"}',
              },
            },
          },
          {
            event: 'response.completed',
            data: { response: { id: 'resp_first', output: [], usage: { output_tokens: 1 } } },
          },
          { event: 'response.created', data: { response: { id: 'resp_prefetch', generate: false } } },
          {
            event: 'response.completed',
            data: { response: { id: 'resp_prefetch', generate: false, usage: { output_tokens: 0 } } },
          },
        ];
        const groups = context.splitWebSocketResponseEvents(events);
        assert.equal(groups.length, 2);
        assert.equal(context.completedResponseFromEvents(groups[0].events).id, 'resp_first');
        assert.deepEqual(
          plain(groups.filter(group => context.isDisplayableWebSocketResponseGroup(group)).map(group => group.responseId)),
          ['resp_first'],
        );
        assert.deepEqual(plain(context.webSocketOutputMessages(groups[0].events)), [
          {
            type: 'message',
            role: 'assistant',
            content: [{
              type: 'tool_use',
              id: 'call_1',
              name: 'shell',
              input: { cmd: 'pwd' },
            }],
          },
        ]);

        assert.deepEqual(plain(context.normalizeDisplayContentBlocks([
          { type: 'input_text', text: 'hello' },
          { type: 'input_image', source: { media_type: 'image/png', data: 'base64-data' } },
          { type: 'tool_result', tool_use_id: 'call_1', content: 'ok' },
        ])), [
          { type: 'input_text', text: 'hello' },
          { type: 'input_image', source: { media_type: 'image/png', data: 'base64-data' } },
          { type: 'tool_result', tool_use_id: 'call_1', content: 'ok' },
        ]);

        assert.deepEqual(plain(context.getMessages({
          instructions: 'Be concise',
          input: [{ role: 'user', content: [{ type: 'input_text', text: 'Hi' }] }],
        })), [
          { role: 'developer', content: [{ type: 'text', text: 'Be concise' }] },
          { role: 'user', content: [{ type: 'input_text', text: 'Hi' }] },
        ]);

        assert.deepEqual(
          plain(context.getRequestTools({
            model: 'gpt-5.6-sol',
            input: [{
              type: 'additional_tools',
              role: 'developer',
              tools: [
                { name: 'exec', description: 'Run a command' },
                { name: 'wait' },
                { name: 'request_user_input' },
              ],
            }],
          }).map(tool => context.toolDisplayName(tool))),
          ['exec', 'wait', 'request_user_input'],
        );

        assert.deepEqual(
          plain(context.getRequestTools({
            tools: [{ name: 'exec' }],
            input: [{
              type: 'additional_tools',
              tools: [{ name: 'exec' }, { name: 'collaboration' }],
            }],
          }).map(tool => context.toolDisplayName(tool))),
          ['exec', 'collaboration'],
        );

        const cursorStepOne = {
          transport: 'cursor-transcript',
          request: {
            method: 'CURSOR_TRANSCRIPT',
            path: '/cursor/transcript/abc/turn/1/step/1',
            body: { messages: [{ role: 'user', content: 'inspect files' }] },
          },
          response: {
            status: 200,
            body: {
              content: [
                { type: 'text', text: 'looking' },
                { type: 'tool_use', name: 'Glob', input: { glob_pattern: 'README*' } },
                { type: 'tool_use', name: 'Shell', input: { command: 'ls' } },
              ],
            },
          },
        };
        const cursorStepTwo = {
          transport: 'cursor-transcript',
          request: {
            method: 'CURSOR_TRANSCRIPT',
            path: '/cursor/transcript/abc/turn/1/step/2',
            body: { messages: [{ role: 'user', content: 'inspect files' }] },
          },
          response: {
            status: 200,
            body: {
              content: [
                { type: 'tool_use', name: 'Read', input: { path: 'README.md', limit: 80 } },
              ],
            },
          },
        };
        const otherCursorSession = {
          transport: 'cursor-transcript',
          request: {
            method: 'CURSOR_TRANSCRIPT',
            path: '/cursor/transcript/other/turn/1/step/1',
            body: { messages: [{ role: 'user', content: 'search the web' }] },
          },
          response: {
            status: 200,
            body: {
              content: [
                { type: 'tool_use', name: 'WebSearch', input: { search_term: 'claude-tap' } },
              ],
            },
          },
        };
        context.cursorStepOne = cursorStepOne;
        context.cursorStepTwo = cursorStepTwo;
        context.otherCursorSession = otherCursorSession;
        vm.runInContext('entries = [cursorStepOne, cursorStepTwo, otherCursorSession]', context);
        assert.deepEqual(
          plain(context.getDetailTools(cursorStepOne, cursorStepOne.request.body, cursorStepOne.response.body)
            .map(tool => [context.toolDisplayName(tool), Object.keys(tool.input_schema.properties)])),
          [['Glob', ['glob_pattern']], ['Shell', ['command']], ['Read', ['path', 'limit']]],
        );
        assert.deepEqual(
          plain(context.getDetailTools(otherCursorSession, otherCursorSession.request.body, otherCursorSession.response.body)
            .map(tool => context.toolDisplayName(tool))),
          ['WebSearch'],
        );
        assert.equal(context.cursorTranscriptConversationKey(cursorStepOne), 'abc');
        assert.equal(context.cursorTranscriptConversationKey(otherCursorSession), 'other');
        assert.equal(
          context.cursorTranscriptConversationKey({ capture: { cursor_transcript_id: 'captured-id' } }),
          'captured-id',
        );
        assert.equal(context.getRequestTools(cursorStepOne.request.body).length, 0);
        vm.runInContext('entries = []', context);

        const codexPrefetchId = 'resp_prefetch_tools';
        const codexVisibleId = 'resp_visible';
        const codexExpanded = context.expandWebSocketResponseEntries([
          {
            transport: 'websocket',
            request: {
              method: 'WEBSOCKET',
              path: '/v1/responses',
              body: {
                model: 'gpt-5.6-sol',
                generate: false,
                input: [{
                  type: 'additional_tools',
                  role: 'developer',
                  tools: [
                    { name: 'exec' },
                    { name: 'wait' },
                    { name: 'request_user_input' },
                    { name: 'collaboration' },
                  ],
                }],
              },
            },
            response: {
              body: {
                id: codexPrefetchId,
                generate: false,
                output: [],
                usage: { input_tokens: 10, output_tokens: 0 },
              },
            },
          },
          {
            transport: 'websocket',
            request: {
              method: 'WEBSOCKET',
              path: '/v1/responses',
              body: {
                model: 'gpt-5.6-sol',
                previous_response_id: codexPrefetchId,
                input: [{ type: 'message', role: 'user', content: [{ type: 'input_text', text: 'Run pwd' }] }],
              },
            },
            response: {
              body: {
                id: codexVisibleId,
                previous_response_id: codexPrefetchId,
                output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'ok' }] }],
                usage: { input_tokens: 20, output_tokens: 2 },
              },
            },
          },
        ]);
        assert.equal(codexExpanded.length, 1);
        assert.deepEqual(
          plain(context.getRequestTools(codexExpanded[0].request.body).map(tool => context.toolDisplayName(tool))),
          ['exec', 'wait', 'request_user_input', 'collaboration'],
        );
        assert.deepEqual(
          plain(context.getMessages(codexExpanded[0].request.body).map(message => message.role)),
          ['user'],
        );

        const compactBundle = {
          __claude_tap_compact_trace__: { version: 1 },
          blobs: {
            hash_1: {
              kind: 'json',
              payload: {
                method: 'POST',
                path: '/v1/responses',
                body: { input: [{ role: 'user', content: 'compact prompt' }] },
              },
            },
          },
          records: [{
            __claude_tap_compact_record__: {
              version: 1,
              refs: [{ path: '/request', hash: 'hash_1', bytes: 100 }],
            },
            record: {
              turn: 1,
              request: {
                __claude_tap_blob_ref__: { version: 1, kind: 'json', hash: 'hash_1' },
              },
              response: {
                status: 200,
                body: {
                  output: [{
                    type: 'message',
                    content: [{
                      type: 'output_text',
                      text: 'marker-shaped user payload',
                      metadata: {
                        __claude_tap_blob_ref__: {
                          version: 1,
                          kind: 'json',
                          hash: 'user-controlled-marker-shape',
                        },
                      },
                    }],
                  }],
                },
              },
            },
          }],
        };
        const fakeUserMarker = {
          __claude_tap_blob_ref__: {
            version: 1,
            kind: 'json',
            hash: 'user-controlled-marker-shape',
          },
        };
        assert.deepEqual(plain(context.materializeCompactTraceBundle(compactBundle)), [{
          turn: 1,
          request: {
            method: 'POST',
            path: '/v1/responses',
            body: { input: [{ role: 'user', content: 'compact prompt' }] },
          },
          response: {
            status: 200,
            body: {
              output: [{
                type: 'message',
                content: [{
                  type: 'output_text',
                  text: 'marker-shaped user payload',
                  metadata: fakeUserMarker,
                }],
              }],
            },
          },
        }]);
        assert.deepEqual(
          plain(context.parseTraceText(JSON.stringify(compactBundle))),
          plain(context.materializeCompactTraceBundle(compactBundle)),
        );

        const legacyCompactBundle = {
          __claude_tap_compact_trace__: { version: 1 },
          blobs: {
            hash_legacy_instructions: {
              kind: 'json',
              payload: 'legacy compact instructions',
            },
            hash_legacy_input: {
              kind: 'json',
              payload: {
                role: 'user',
                content: [{ type: 'input_text', text: 'legacy compact input item' }],
              },
            },
          },
          records: [{
            __claude_tap_compact_record__: {
              version: 1,
              encoding: 'json-blob-ref',
            },
            record: {
              turn: 2,
              request: {
                body: {
                  instructions: {
                    __claude_tap_blob_ref__: { version: 1, kind: 'json', hash: 'hash_legacy_instructions' },
                  },
                  input: [
                    {
                      __claude_tap_blob_ref__: { version: 1, kind: 'json', hash: 'hash_legacy_input' },
                    },
                    {
                      role: 'user',
                      content: [{ type: 'input_text', text: 'keep marker shape' }],
                      metadata: fakeUserMarker,
                    },
                  ],
                },
              },
              response: { body: { output: [] } },
            },
          }],
        };
        assert.deepEqual(plain(context.materializeCompactTraceBundle(legacyCompactBundle)), [{
          turn: 2,
          request: {
            body: {
              instructions: 'legacy compact instructions',
              input: [
                {
                  role: 'user',
                  content: [{ type: 'input_text', text: 'legacy compact input item' }],
                },
                {
                  role: 'user',
                  content: [{ type: 'input_text', text: 'keep marker shape' }],
                  metadata: fakeUserMarker,
                },
              ],
            },
          },
          response: { body: { output: [] } },
        }]);

        /* ── normalizeUsage: provider-aware cache flag ── */

        // OpenAI-style: cached_tokens embedded in prompt_tokens via details
        const openaiUsage = context.normalizeUsage({
          prompt_tokens: 100,
          completion_tokens: 50,
          prompt_tokens_details: { cached_tokens: 60 },
        });
        assert.equal(openaiUsage.input_tokens, 100);
        assert.equal(openaiUsage.cache_read_input_tokens, 60);
        assert.equal(openaiUsage._cache_read_in_input, true);

        // Claude/Anthropic-style: cache_read_input_tokens separate from input_tokens
        const claudeUsage = context.normalizeUsage({
          input_tokens: 40,
          output_tokens: 20,
          cache_read_input_tokens: 60,
          cache_creation_input_tokens: 10,
        });
        assert.equal(claudeUsage.input_tokens, 40);
        assert.equal(claudeUsage.cache_read_input_tokens, 60);
        assert.equal(claudeUsage._cache_read_in_input, false);

        // Bedrock Converse-style camelCase: cacheReadInputTokens is a separate bucket
        const bedrockUsage = context.normalizeUsage({
          inputTokens: 9,
          outputTokens: 1,
          cacheReadInputTokens: 12,
          cacheWriteInputTokens: 2,
        });
        assert.equal(bedrockUsage.input_tokens, 9);
        assert.equal(bedrockUsage.cache_read_input_tokens, 12);
        assert.equal(bedrockUsage.cache_creation_input_tokens, 2);
        assert.equal(bedrockUsage._cache_read_in_input, false);

        /* OpenAI Realtime spells the bucket singular. pricing.py already lists it
           among the Realtime modality buckets, so skipping it here left the whole
           prompt billed at the input rate with no cache read shown. */
        const realtimeUsage = context.normalizeUsage({
          input_tokens: 51000,
          output_tokens: 100,
          input_token_details: { cached_tokens: 50000 },
        });
        assert.equal(realtimeUsage.cache_read_input_tokens, 50000,
          'a Realtime cache hit must be read out of the singular details bucket');
        assert.equal(realtimeUsage._cache_read_in_input, true);

        // No cache data at all: flag should be absent
        const noCacheUsage = context.normalizeUsage({ input_tokens: 100, output_tokens: 50 });
        assert.equal(noCacheUsage.cache_read_input_tokens, undefined);
        assert.equal(noCacheUsage._cache_read_in_input, undefined);

        /* ── Cache hit rate denominator correctness ── */

        // Simulate OpenAI-style: cache embedded in input → rate = 60/100 = 60%
        //   denominator = input_tokens = 100
        const openaiRate = Math.round(60 / 100 * 100);
        assert.equal(openaiRate, 60);

        // Simulate Claude-style: cache separate → total input-side = 40+60+10 = 110
        //   rate = 60/110 = 55% (NOT 60/40 = 150% which is the old buggy result)
        const claudeTotalInput = 40 + 60 + 10;
        const claudeRate = Math.round(60 / claudeTotalInput * 100);
        assert.equal(claudeRate, 55);
        assert.ok(claudeRate <= 100, 'Claude-style rate must not exceed 100%');

        /* ── Direct DOM test: #stat-cache-hit-rate via applyFilter() ── */

        context.assert = assert;
        context.element = element;

        vm.runInContext(`
          // Persistent stat elements so applyFilter can set textContent
          const _statEls = {};
          document.querySelector = function (sel) {
            if (typeof sel === 'string' && sel.startsWith('#')) {
              const id = sel.slice(1);
              if (!_statEls[id]) _statEls[id] = element();
              return _statEls[id];
            }
            return element();
          };
          // Stub heavy rendering helpers irrelevant to stat computation
          renderSidebar = function () {};
          updatePositionIndicator = function () {};
          renderToolFilter = function () {};
          renderPathFilter = function () {};
          renderTracePathBar = function () {};

          function makeUsageEntry(usage, path) {
            return {
              request: { path: path || '/v1/messages', method: 'POST', body: {} },
              response: { body: { usage } },
              turn: '1',
              duration_ms: 100,
            };
          }

          // Claude-style: cache_read separate from input → 60/(40+60+10)=55%
          entries = [makeUsageEntry({
            input_tokens: 40, output_tokens: 20,
            cache_read_input_tokens: 60, cache_creation_input_tokens: 10,
          })];
          activePaths = new Set(['/v1/messages']);
          searchQuery = '';
          activeTools = null;
          applyFilter();
          assert.equal(_statEls['stat-cache-hit-rate'].textContent, '55%',
            'Claude-style direct DOM: expected 55%');
          assert.equal(_statEls['stat-cache-hit-rate-group'].style.display, 'flex',
            'Claude-style direct DOM: group should be visible');

          // OpenAI-style: cache embedded in input → 60/100=60%
          entries = [makeUsageEntry({
            prompt_tokens: 100, completion_tokens: 50,
            prompt_tokens_details: { cached_tokens: 60 },
          })];
          applyFilter();
          assert.equal(_statEls['stat-cache-hit-rate'].textContent, '60%',
            'OpenAI-style direct DOM: expected 60%');

          // Bedrock camelCase: cache_read separate from input → 12/(9+12+2)=52%
          entries = [makeUsageEntry({
            inputTokens: 9, outputTokens: 1,
            cacheReadInputTokens: 12, cacheWriteInputTokens: 2,
          })];
          applyFilter();
          assert.equal(_statEls['stat-cache-hit-rate'].textContent, '52%',
            'Bedrock camelCase direct DOM: expected 52%');

          // No cache data: group should be hidden
          entries = [makeUsageEntry({ input_tokens: 100, output_tokens: 50 })];
          applyFilter();
          assert.equal(_statEls['stat-cache-hit-rate-group'].style.display, 'none',
            'No-cache direct DOM: group should be hidden');

          // Mixed providers: OpenAI(100,cache=60) + Claude(40,cache_read=60,create=10)
          // denom = 100 + 110 = 210, cache_read = 120, rate = 57%
          entries = [
            makeUsageEntry({
              prompt_tokens: 100, completion_tokens: 50,
              prompt_tokens_details: { cached_tokens: 60 },
            }),
            makeUsageEntry({
              input_tokens: 40, output_tokens: 20,
              cache_read_input_tokens: 60, cache_creation_input_tokens: 10,
            }),
          ];
          applyFilter();
          assert.equal(_statEls['stat-cache-hit-rate'].textContent, '57%',
            'Mixed-provider direct DOM: expected 57%');

          // Mixed cached and uncached entries: uncached input still belongs in denominator
          // denom = OpenAI input 100 + uncached input 100, cache_read = 60, rate = 30%
          entries = [
            makeUsageEntry({
              prompt_tokens: 100, completion_tokens: 50,
              prompt_tokens_details: { cached_tokens: 60 },
            }),
            makeUsageEntry({ input_tokens: 100, output_tokens: 10 }),
          ];
          applyFilter();
          assert.equal(_statEls['stat-cache-hit-rate'].textContent, '30%',
            'Mixed cached/uncached direct DOM: expected 30%');

          /* ── Cost stats: display and summation only ── */

          function makeCostEntry(requestId, cost, saved) {
            const entry = makeUsageEntry({ input_tokens: 100, output_tokens: 10 });
            entry.request_id = requestId;
            if (cost !== undefined) { entry.cost = cost; entry.saved = saved; }
            return entry;
          }

          /* Sub-cent totals must not collapse to $0.00 and report a paid trace
             as free. */
          assert.equal(formatCostUsd(0.0004), '$0.0004');
          assert.equal(formatCostUsd(1.5), '$1.50');
          assert.equal(formatCostUsd(-0.25), '-$0.25');
          assert.equal(formatCostUsd(0), '$0.00');
          assert.equal(formatCostUsd('nope'), '');
          assert.equal(formatCostUsd(Infinity), '');
          /* 100 uncached deepseek/deepseek-chat tokens are $0.000028; toFixed(4)
             would render that paid turn as $0.0000. */
          assert.equal(formatCostUsd(0.000028), '$0.000028');
          assert.equal(formatCostUsd(100 * 1.4e-7), '$0.000014');

          /* Drag-and-drop traces never reach Python, so nothing is priced. */
          EMBEDDED_COST_INDEX = undefined;
          EMBEDDED_PRICING_META = undefined;
          entries = [makeCostEntry('req_a')];
          applyFilter();
          assert.equal(entryCost(entries[0]), null, 'unpriced entry must yield null');
          assert.equal(pricingMeta(), null, 'no provenance without EMBEDDED_PRICING_META');
          assert.equal(_statEls['stat-cost-group'].style.display, 'none',
            'cost group hidden when nothing is priced');
          assert.equal(_statEls['stat-saved-group'].style.display, 'none',
            'saved group hidden when nothing is priced');

          /* Lazy mode: cost rides on the entry itself. */
          EMBEDDED_PRICING_META = { source: 'litellm', as_of: '2026-08-19' };
          entries = [makeCostEntry('req_a', 0.5, 0.25), makeCostEntry('req_b', 0.25, 0.125)];
          applyFilter();
          assert.equal(_statEls['stat-cost'].textContent, '$0.75');
          assert.equal(_statEls['stat-saved'].textContent, '$0.38');
          assert.equal(_statEls['stat-cost-group'].style.display, 'flex');
          assert.ok(_statEls['stat-cost-group'].title.indexOf('litellm') >= 0,
            'price source must be disclosed');
          assert.ok(_statEls['stat-cost-group'].title.indexOf('2026-08-19') >= 0,
            'price table date must be disclosed');

          /* Records mode: cost comes from the index, keyed by request id. */
          entries = [makeCostEntry('req_a'), makeCostEntry('req_b')];
          EMBEDDED_COST_INDEX = { req_a: { cost: 0.02, saved: 0.01 }, req_b: { cost: 0.03, saved: 0.02 } };
          applyFilter();
          assert.equal(_statEls['stat-cost'].textContent, '$0.05');
          assert.equal(_statEls['stat-saved'].textContent, '$0.03');

          /* A partially priced set must say so on the face of the stat, not
             only in a tooltip. */
          entries = [makeCostEntry('req_a'), makeCostEntry('req_missing')];
          applyFilter();
          assert.equal(_statEls['stat-cost'].textContent, '$0.02+',
            'partial totals are marked with a trailing +');
          assert.ok(_statEls['stat-cost-group'].title.indexOf('1') >= 0,
            'tooltip must count the excluded turns');

          /* Signed per-entry savings: a write-only turn costs more than an
             uncached one, but the displayed total is clamped at zero. */
          EMBEDDED_COST_INDEX = { req_a: { cost: 0.02, saved: -0.01 } };
          entries = [makeCostEntry('req_a')];
          applyFilter();
          assert.equal(entryCost(entries[0]).saved, -0.01, 'per-entry saved stays signed');
          assert.equal(_statEls['stat-saved'].textContent, '$0.00',
            'aggregate saved is clamped for display');

          /* Cost shows even when the token stats are hidden for lack of usage. */
          EMBEDDED_COST_INDEX = { req_nousage: { cost: 0.42, saved: 0.1 } };
          entries = [{
            request: { path: '/v1/messages', method: 'POST', body: {} },
            response: { body: {} },
            request_id: 'req_nousage',
            turn: '1',
            duration_ms: 100,
          }];
          applyFilter();
          assert.equal(_statEls['stat-input-group'].style.display, 'none',
            'token breakdown hidden without usage');
          assert.equal(_statEls['stat-cost'].textContent, '$0.42',
            'cost must not be gated on token totals');

          /* Live mode and the records API serve raw records with no generated
             index, so Python attaches the costs to the record itself. */
          EMBEDDED_COST_INDEX = {};
          const liveEntry = makeCostEntry('req_live');
          liveEntry._cost_index = { req_live: { cost: 0.11, saved: 0.05 } };
          entries = [liveEntry];
          applyFilter();
          assert.equal(entryCost(entries[0]).cost, 0.11, 'record-borne cost must be read');
          assert.equal(_statEls['stat-cost'].textContent, '$0.11');

          /* A WebSocket record split into several entries carries one keyed set
             per derived entry. */
          const wsFirst = makeCostEntry('req_ws:1');
          const wsSecond = makeCostEntry('req_ws:2');
          const wsIndex = { 'req_ws:1': { cost: 0.01, saved: 0 }, 'req_ws:2': { cost: 0.02, saved: 0 } };
          wsFirst._cost_index = wsIndex;
          wsSecond._cost_index = wsIndex;
          entries = [wsFirst, wsSecond];
          applyFilter();
          assert.equal(_statEls['stat-cost'].textContent, '$0.03');

          /* The upstream price file changes several times a day, so the tooltip
             names the commit as well as the date. */
          EMBEDDED_PRICING_META = { source: 'litellm', as_of: '2026-08-19', upstream_commit: '24fc3f721c4086a0ab8318f15a005309a8a55512' };
          entries = [makeCostEntry('req_a', 0.5, 0.25)];
          applyFilter();
          assert.ok(_statEls['stat-cost-group'].title.indexOf('24fc3f721c40') >= 0,
            'price snapshot commit must be disclosed');

          /* Gemini keeps reasoning tokens out of candidatesTokenCount but bills
             them at the output rate. */
          assert.equal(
            normalizeUsage({ promptTokenCount: 1000, candidatesTokenCount: 200, thoughtsTokenCount: 800 }).output_tokens,
            1000,
            'thinking tokens belong in the billed output total');

          /* Lazy stubs must keep the cost Python put on the metadata record. */
          const stub = buildStubEntry({
            request_id: 'req_stub',
            path: '/v1/messages',
            method: 'POST',
            cost: 0.07,
            uncached_cost: 0.2,
            saved: 0.13,
            priced_model: 'claude-sonnet-4-20250514',
            long_context: false,
          }, 0);
          assert.equal(stub.cost, 0.07, 'stub must carry cost');
          assert.equal(stub.saved, 0.13, 'stub must carry savings');
          assert.equal(stub.priced_model, 'claude-sonnet-4-20250514');

          /* Cache provenance travels on the metadata; re-inferring it from the
             model name misread every embedded-cache turn, because metadata
             carries cache_creation_input_tokens even when it is zero. */
          const embeddedStub = buildStubEntry({
            request_id: 'req_embedded',
            path: '/v1/chat/completions',
            method: 'POST',
            model: 'gpt-4o',
            input_tokens: 51000,
            output_tokens: 100,
            cache_read_input_tokens: 50000,
            cache_creation_input_tokens: 0,
            cache_read_in_input: true,
          }, 0);
          assert.equal(getUsage(embeddedStub)._cache_read_in_input, true,
            'an embedded-cache turn must not be counted against a doubled denominator');

          const separateStub = buildStubEntry({
            request_id: 'req_separate',
            path: '/v1/messages',
            method: 'POST',
            model: 'claude-sonnet-4-20250514',
            input_tokens: 120,
            cache_read_input_tokens: 40000,
            cache_creation_input_tokens: 2000,
            cache_read_in_input: false,
          }, 0);
          assert.equal(getUsage(separateStub)._cache_read_in_input, false,
            'a separate-bucket turn keeps its own denominator');

          /* A turn that reported no tokens has no unknown price to report. The
             full record has no usage object at all, so the stub must not invent
             an empty one -- it is truthy, and lazy mode alone would count every
             count_tokens call as a turn whose price could not be determined. */
          const tokenCountStub = buildStubEntry({
            request_id: 'req_count',
            path: '/v1/messages/count_tokens',
            method: 'POST',
            model: 'claude-sonnet-4-20250514',
          }, 0);
          assert.equal(getUsage(tokenCountStub), null,
            'a usage-free turn must not read as usage-bearing');

          /* Metadata written before the flag existed still gets the name check. */
          const legacyStub = buildStubEntry({
            request_id: 'req_legacy',
            path: '/v1/chat/completions',
            method: 'POST',
            model: 'gpt-4o',
            input_tokens: 51000,
            cache_read_input_tokens: 50000,
            cache_creation_input_tokens: 0,
          }, 0);
          assert.equal(getUsage(legacyStub)._cache_read_in_input, true,
            'a flag-less OpenAI stub still reads as embedded');

          /* ── Subscription turns: absent cost with a stated reason ── */

          /* A ChatGPT-subscription turn is not a priced turn and not an
             unknown-price turn either, so it must not land in the "no known
             price" count. */
          const subStub = buildStubEntry({
            request_id: 'req_sub',
            path: '/backend-api/codex/responses',
            method: 'POST',
            subscription: true,
          }, 0);
          assert.equal(subStub.subscription, true, 'stub must carry the subscription flag');
          assert.equal(subStub.cost, undefined, 'a subscription stub carries no cost');

          EMBEDDED_COST_INDEX = {};
          assert.equal(isSubscriptionEntry(subStub), true, 'stub flag must be recognised');
          assert.equal(entryCost(subStub), null, 'a subscription turn has no priced cost');
          assert.deepEqual(entryCostRecord(subStub), { subscription: true });

          /* Live mode and the records API carry the flag on the record instead. */
          const subLive = makeCostEntry('req_sub_live');
          subLive._cost_index = { req_sub_live: { subscription: true } };
          assert.equal(isSubscriptionEntry(subLive), true, 'record-borne flag must be recognised');
          assert.equal(entryCost(subLive), null);

          /* Records mode reads it from the generated index. */
          const subIndexed = makeCostEntry('req_sub_idx');
          EMBEDDED_COST_INDEX = { req_sub_idx: { subscription: true } };
          assert.equal(isSubscriptionEntry(subIndexed), true, 'indexed flag must be recognised');
          assert.equal(entryCost(subIndexed), null);

          assert.equal(isSubscriptionEntry(makeCostEntry('req_plain', 0.5, 0.25)), false,
            'a priced turn is not a subscription turn');
          assert.equal(isSubscriptionEntry(null), false);
          assert.equal(entryCostRecord(null), null);

          /* Subscription turns are counted apart from unpriceable ones, and the
             total is still marked partial because they are missing from it. */
          EMBEDDED_COST_INDEX = { req_a: { cost: 0.02, saved: 0.01 }, req_sub_idx: { subscription: true } };
          entries = [makeCostEntry('req_a'), makeCostEntry('req_sub_idx')];
          applyFilter();
          assert.equal(_statEls['stat-cost'].textContent, '$0.02+',
            'a subscription turn keeps the total marked partial');
          const subTitle = _statEls['stat-cost-group'].title;
          assert.ok(subTitle.indexOf('subscription') >= 0 || subTitle.indexOf('ChatGPT') >= 0,
            'tooltip must name the subscription reason');
        `, context);
        """
    )

    subprocess.run(["node", "-e", script, str(REPO_ROOT)], check=True, capture_output=True, text=True)
