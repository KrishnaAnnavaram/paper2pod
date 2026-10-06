# ASD-STE100 Simplified Technical English: the paper2pod writing standard

Use these rules for the paper2pod `README.md` and for this file. Section 3 gives the
**project vocabulary**: the technical names and the technical verbs of paper2pod. Each term has
only one meaning. Do not use the synonyms in the "Do not use" column.

## 1. The writing rules

### Words

1. Use one word for one meaning, and one meaning for one word. Do not use synonyms for variety.
2. Use a word only as one part of speech. For example, "test" is a noun or a verb, "check" is a verb.
3. Do not use phrasal verbs (`set up`, `carry out`, `find out`, `pick up`, `look up`, `come up with`).
   Use one verb: "prepare", "do", "find", "get", "make".
4. Do not use an "-ing" form as a noun or an adjective ("the running job", "after indexing").
   Exception: a technical name, a file name, a command or a status value.
5. Do not use contractions (`don't`, `it's`, `can't`). Do not use slang or idioms
   (`out of the box`, `under the hood`, `at a glance`, `gotcha`, `bells and whistles`).
6. Do not use `and/or`. Write "A, B or both".
7. Do not use `should`, `could`, `would` or `may` for instructions. Use "must" for a rule, the
   imperative for a step and "can" for a possibility.
8. Keep the articles "a", "an" and "the" in sentences.
9. Do not make a noun cluster of more than three words. A technical name is one word.

### Sentences

1. A procedural sentence (an instruction) has a maximum of **20 words**.
2. A descriptive sentence has a maximum of **25 words**.
3. Write one instruction in one sentence.
4. Use the imperative for an instruction: "Run the tests." Not `The tests should be run.`
5. Use the active voice. Use the passive voice only when the agent of the action is not important.
6. Use only the simple present, the simple past and the simple future.
7. Put a condition before the instruction: "If the index is stale, build it again."
8. Do not use semicolons in sentences. Write two sentences.

### Paragraphs, notes and warnings

1. A paragraph has one topic and a maximum of **6 sentences**. Start with the topic sentence.
2. A warning or a caution starts with a clear command. Then it gives the reason.
3. A note gives information. It does not give an instruction.
4. Use a vertical list for a sequence or a set of conditions. Each item of a numbered procedure is one step.

### Tables, headings and diagrams

1. A table cell can be a short phrase. If a cell has a sentence, the sentence obeys the rules.
2. A heading is a noun phrase ("The cost model") or an imperative ("Run the demo").
   Do not start a heading with an "-ing" form.
3. A diagram label is a short phrase. Use the same terms as the text.

### What STE does not change

Code, commands, file names, paths, field names, environment variables, status values, enum values,
product names and URLs stay exactly as they are. They are technical names. Put them in backticks.

## 2. General words to replace

| Do not use | Use |
|---|---|
| utilize, leverage | use |
| in order to | to |
| set up | prepare, install, configure |
| carry out, perform | do |
| make sure, ensure | make sure (allowed), or "check that" |
| a lot of, lots of | many, much |
| e.g., i.e. | for example, that is |
| should (instruction) | must (rule) / imperative (step) |
| might, may (possibility) | can |
| very, really, just, simply, easily | (delete) |
| seamless, robust, powerful, blazing | (delete or give a measured fact) |

## 3. Project vocabulary

### 3.1 Technical names (nouns)

| Term | Meaning | Do not use |
|---|---|---|
| **paper** | One arXiv paper: its metadata (`Paper`) and its full text | article, document, publication |
| **paper reference** | The text that identifies a paper: an arXiv ID, a versioned ID or an arXiv URL | paper ID (for a URL), link |
| **paper source** | The adapter that searches, resolves and fetches papers (`ArxivClient` or `LocalPaperSource`) | provider (for papers), loader |
| **sample paper** | The fictional paper in `src/paper2pod/demo/sample_paper.txt` for the offline demo | test paper, dummy paper |
| **section** | One part of the paper text between two detected headings (`Section`) | chapter (for the paper), part |
| **back matter** | The references, bibliography, acknowledgements, appendices, supplementary material and checklist | appendix (for all of these) |
| **outline** | The list of outline items that the outline stage makes | summary (for the list), plan |
| **outline item** | One group of sections with a summary, key points and a weight (`OutlineItem`) | topic, part |
| **weight** | The square root of the word count of an outline item. It sets the word budget share | size, importance |
| **podcast** | The final audio file (`podcast.wav`, optional `podcast.mp3`) for one job | episode, show, recording |
| **script** | The full dialogue for one podcast (`Script`, `script.json`) | transcript, text |
| **segment** | One part of the script that the LLM writes in one call: the opening, a body part or the wrap-up | section (for the script), block |
| **segment plan** | The title, kind, word budget, notes and token limit of one segment (`SegmentPlan`) | segment spec |
| **word budget** | The number of words that a podcast or a segment must have | word target, quota |
| **tolerance** | The permitted relative difference between the word count and the word budget | margin, slack |
| **turn** | One spoken contribution of one speaker (`Turn`: `speaker`, `text`, `direction`) | line, utterance |
| **direction** | A delivery hint for a turn, for example `laughs`. paper2pod does not speak it | stage direction, cue (for the field) |
| **cue** | A bracketed delivery hint in the LLM text, for example `[laughs]`. paper2pod moves it to the direction | tag |
| **speaker** | One person in the dialogue, with a name, a role, a voice style and an optional voice | host (for all speakers), character |
| **role** | The function of a speaker: `host`, `expert` or `guest` | part, persona |
| **voice style** | The approximate sound of a voice: `male`, `female`, `neutral` or `any` | gender, timbre |
| **voice** | One named TTS voice from the voice catalog, for example `nova` | speaker (for a voice) |
| **voice catalog** | The six OpenAI voices and their voice styles (`OPENAI_VOICES`) | voice list, voice bank |
| **chunk** | A part of a text that fits one LLM call (12,000 characters) or one TTS call (4,000 characters) | piece, batch |
| **clip** | The PCM audio of one turn | sample, fragment |
| **chapter** | The start time and title of one segment in the podcast (`chapters.json`) | marker, timestamp |
| **job** | One request to make one podcast, with a status, a stage, a progress value and outputs | task, run |
| **job directory** | The folder `data/jobs/<job_id>/` that holds all files of one job | workdir (in prose), output folder |
| **job store** | The registry that keeps one `job.json` file for each job (`JobStore`) | database, queue |
| **job runner** | The thread pool that runs jobs in the background (`JobRunner`) | worker, scheduler |
| **stage** | One of the seven pipeline steps: `fetch`, `parse`, `outline`, `script`, `validate`, `tts`, `mix` | phase, step (for a stage) |
| **pipeline** | The seven stages in sequence (`Pipeline.run`) | workflow (for the code), chain |
| **front-end** | A way to start and follow jobs: the CLI, the HTTP API, the Streamlit UI or the chat session | client, interface |
| **adapter** | A class that hides one external service behind a small interface (LLM, TTS or paper source) | wrapper, plugin |
| **backend** | The adapter family: `openai` (real services) or `fake` (offline, deterministic) | mode, engine (for the family) |
| **LLM** | The chat language model that writes summaries and segments | model (alone), AI |
| **TTS engine** | The adapter that changes text into PCM audio (`OpenAITTS` or `FakeTTS`) | voice model, synthesizer |
| **metrics file** | The quality report `metrics.json` of one job | report file, stats |
| **grounding score** | The fraction of checked sentences whose numbers and acronyms all occur in the paper | accuracy, factuality score |
| **cache** | The files in `data/cache/` that paper2pod reads again instead of a new network call | store (for the cache) |
| **intent** | The kind of chat request: `help`, `status`, `cancel`, `search` or `make` | command (in the chat) |

### 3.2 Technical verbs

| Verb | Meaning |
|---|---|
| **search** | Send a free-text query to the paper source and get a list of papers |
| **resolve** | Change a paper reference into paper metadata |
| **fetch** | Get the full text of a paper (download and extract the PDF, or read the sample paper) |
| **parse** | Clean the paper text, split it into sections and remove the back matter |
| **summarize** | Make the summary and the key points of one outline item with the LLM |
| **plan** | Divide the word budget of the podcast into segment plans |
| **write** | Make the turns of one segment with the LLM |
| **regenerate** | Send a segment request to the LLM again, with feedback about the last answer |
| **trim** | Cut the turns of a segment at a sentence end so that they fit the upper word limit |
| **validate** | Check the script for format problems, grounding and readability, and record the results |
| **synthesize** | Change the text of one chunk into PCM audio with the TTS engine |
| **mix** | Join the clips with pauses, normalize the loudness and write the WAV file |
| **normalize** | Scale a clip to the target loudness (−20 dBFS RMS, peak at most 0.95) |
| **submit** | Give a job to the job runner. The call returns at once |
| **poll** | Read the status of a job again until it is finished |
| **cancel** | Ask the job runner to stop a job at the next check |
| **retry** | Do a failed network call again after a delay (only for transient errors) |
