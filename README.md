# CM3070 Final Project

## To-Do List

- [x] Verify the full project flow works end to end
- [x] Fix the backend logging issue in `project/backend/src/app.py`
- [x] Confirm the correct environment file and update setup instructions consistently
- [x] Make unit tests discoverable and runnable
- [ ] Collect evaluation evidence such as screenshots, results, and failure cases
- [ ] Finalise the report structure and submission content
- [ ] Prepare the 3 to 5 minute project demonstration video
- [x] Fix the environment filename inconsistency in the setup section
- [x] Use one environment file consistently across Windows and macOS instructions
- [x] Separate draft report instructions from final report instructions clearly

- [x] Add a short `How to Run` summary near the top of the README
- [x] Add a `Known Issues` section
- [x] Add a `Project Status` section
- [x] Add a `Models Used` section listing the active models in the project
- [x] Add a `Repository Link for Submission` section
- [x] Add a `Video Checklist` section for the final submission requirements
- [ ] Remove repeated or unnecessary wording so the README stays practical and clear
- [ ] Test the system with a wider variety of food and non-food images
- [ ] Document incorrect predictions, failure cases, and system limitations
- [ ] Confirm the public repository is clean and submission-ready

- [ ] Perform a final full submission-readiness review of the project

## Modularisation To-Do List

- [ ] Split database functions out of `project/featured_prototype.py` into a dedicated database module
- [ ] Split encryption helpers into a dedicated encryption module
- [ ] Split nutrition loading and lookup logic into a dedicated nutrition module
- [ ] Split model loading and inference functions into a dedicated models module
- [ ] Split semantic matching logic into a dedicated retrieval or matching module
- [ ] Split trend and analytics functions into a dedicated analytics module
- [ ] Move CLI demo flow out of `project/featured_prototype.py` into a smaller entry-focused file
- [ ] Reduce direct coupling between `project/backend/src/app.py` and `project/featured_prototype.py`
- [ ] Keep each module focused on one responsibility
- [ ] Update imports after refactoring so the backend and tests still run cleanly
- [ ] Extend unit tests after refactoring to confirm behavior has not changed
- [ ] Update README structure documentation after modularisation is complete

## How to Run

1. Create the environment with `conda env create -f env.yml`
2. Activate it with `conda activate cm3070`
3. Start the backend with `cd project/backend/src && python -m uvicorn app:app --reload`
4. Open `http://127.0.0.1:8000`
5. Run tests with `python project/tests/run_tests.py`

## Project Status

- Core image-to-log pipeline is implemented
- Web interface is implemented
- Logging, trends, daily logs, and delete flow are implemented
- Manual end-to-end validation has been completed
- Unit tests are implemented and saving reports
- Wider image testing, final evidence collection, and submission preparation are still in progress

## Models Used

- `prithivMLmods/Food-or-Not-SigLIP2` for food vs non-food gating
- `Albertbeta123/resnet-50-chinese-food` for food image classification
- `torchvision ResNet18 (ImageNet pretrained)` as a general fallback classifier when the Asian food classifier confidence is below the trigger threshold
- `sentence-transformers/all-MiniLM-L6-v2` for semantic text matching to nutrition entries
- `google/flan-t5-base` for NLP-based 7-day trend interpretation and dietary advice generation

## Known Issues

- The system still struggles with dishes that contain multiple different food items in the same image
- Confidence scores can still be lower than expected even when similar or repeated food types are presented
- `project/featured_prototype.py` is still too large and should be modularised
- Final report evidence such as screenshots, failure cases, and limitation analysis still needs to be collected

## Repository Link for Submission

- Public repository link: `Add final public GitHub repository URL here`

## Video Checklist

- [ ] Record a 3 to 5 minute demonstration video
- [ ] Show the main workflow from upload to logging and trends
- [ ] Explain the models and overall pipeline briefly
- [ ] Include visuals such as UI screens and outputs
- [ ] Use your own spoken audio
- [ ] Do not use AI-generated voice
- [ ] Keep the video within the required time limit

## End-to-End Pass/Fail Checklist

- [x] Pass / [ ] Fail: Backend starts successfully with `uvicorn`
- [x] Pass / [ ] Fail: Frontend loads at `http://127.0.0.1:8000`
- [x] Pass / [ ] Fail: Food image upload works
- [x] Pass / [ ] Fail: Image preview displays correctly
- [x] Pass / [ ] Fail: Prediction results are returned
- [x] Pass / [ ] Fail: Calories per 100g are shown
- [x] Pass / [ ] Fail: Logging a selected result works
- [x] Pass / [ ] Fail: Logging `None of the above` works
- [x] Pass / [ ] Fail: Portion size is stored correctly
- [x] Pass / [ ] Fail: Date selection works for today
- [x] Pass / [ ] Fail: Date selection works for past dates
- [x] Pass / [ ] Fail: 7-day trend data updates correctly
- [x] Pass / [ ] Fail: Daily logs can be viewed
- [x] Pass / [ ] Fail: Log deletion works
- [x] Pass / [ ] Fail: Non-food images are rejected correctly
- [x] Pass / [ ] Fail: Invalid portion values are blocked correctly

## Setup

This repository contains the current project prototype, backend, frontend, data files, and report support material.

### Windows Setup

#### 1. Create and activate the Conda environment

```powershell
conda env create -f env.yml
conda activate cm3070
```

#### 2. Install required Python packages

```powershell
pip install sentence-transformers transformers timm cryptography fastapi uvicorn[standard] python-multipart
```

#### 3. Run the CLI prototype

```powershell
python project/backend/cli_launch.py --num-images 3
```

Optional example:

```powershell
python project/backend/cli_launch.py --image-dir project/backend/data/sample_images --num-images 5
```

#### 4. Run the web interface

```powershell
cd project/backend/src
python -m uvicorn app:app --reload
```

Then open `http://127.0.0.1:8000`.

#### 5. Encryption key configuration

By default, a key file is created at `project/backend/data/logs/db.key`.

Optional environment override:

```powershell
$env:CALORIE_DB_KEY = "<base64-key>"
```

#### 6. Run tests

```powershell
python -m unittest discover -s project/tests
```

#### 7. Optional dataset reduction step

```powershell
python project/backend/DataExtract/extract_openfoodfacts.py
```

### macOS Setup

#### 1. Create and activate the Conda environment

```bash
conda env create -f env.yml
conda activate cm3070
```

#### 2. Install required Python packages

```bash
pip install sentence-transformers transformers timm cryptography fastapi uvicorn[standard] python-multipart
```

#### 3. Run the CLI prototype

```bash
python project/backend/cli_launch.py --num-images 3
```

Optional example:

```bash
python project/backend/cli_launch.py --image-dir project/backend/data/sample_images --num-images 5
```

#### 4. Run the web interface

```bash
cd project/backend/src
python -m uvicorn app:app --reload
```

Then open `http://127.0.0.1:8000`.

#### 5. Encryption key configuration

By default, a key file is created at `project/backend/data/logs/db.key`.

Optional environment override:

```bash
export CALORIE_DB_KEY="<base64-key>"
```

#### 6. Run tests

```bash
python -m unittest discover -s project/tests
```

#### 7. Optional dataset reduction step

```bash
python project/backend/DataExtract/extract_openfoodfacts.py
```

## Project Structure

- `project/backend/cli_launch.py`: CLI entry point
- `project/featured_prototype.py`: main pipeline logic
- `project/backend/src/app.py`: FastAPI backend
- `project/frontend/index.html`: frontend interface
- `project/backend/data/`: nutrition data, sample images, and logs
- `project/tests/`: unit tests

## Data and Outputs

- Primary nutrition CSV: `project/backend/data/asian_openfoodfacts.csv`
- Fallback nutrition CSV: `project/backend/data/generic_openfoodfacts.csv`
- SQLite log database: `project/backend/data/logs/calorie_log.db`
- Encryption key: `project/backend/data/logs/db.key`
- Logged image copies: `project/backend/data/logs/images`

## SQLite Inspection

Use these commands to inspect the SQLite database directly.

Open the database:

```bash
sqlite3 project/backend/data/logs/calorie_log.db
```

List tables:

```sql
.tables
```

Show table schema:

```sql
.schema log
.schema nutrition
.schema nutrition_macros
```

View all log rows:

```sql
SELECT * FROM log;
```

View recent log entries:

```sql
SELECT id, timestamp, food_type, calories_per_100g, portion_grams, calories_total
FROM log
ORDER BY timestamp DESC
LIMIT 20;
```

View nutrition entries:

```sql
SELECT * FROM nutrition LIMIT 20;
```

View macro entries:

```sql
SELECT * FROM nutrition_macros LIMIT 20;
```

Count log rows:

```sql
SELECT COUNT(*) FROM log;
```

Exit SQLite:

```sql
.quit
```

## Notes

- The first run may download model weights and embedding models, so internet access may be required.
- The pipeline uses CUDA if available, otherwise CPU.

## Unit Testing

### Test Coverage

The unit test suite covers the main non-ML logic and the backend API behavior.

Tests currently cover:

- encryption and decryption of logged fields
- nutrition table seeding from CSV
- SQLite logging and retrieval
- calorie lookup behavior
- 7-day daily totals calculation
- homepage route loading
- prediction route for food and non-food cases
- image preview route
- logging a selected prediction
- logging `None of the above`
- invalid logging inputs such as bad portion size or invalid date
- trends endpoint
- daily logs endpoint
- delete log endpoint

### Test File

- Main test suite: `project/tests/test_unit.py`
- Test runner with saved report output: `project/tests/run_tests.py`

### How to Run Tests

Activate the project environment first:

```bash
conda activate cm3070
```

Run the full suite with the built-in runner:

```bash
python project/tests/run_tests.py
```

### Test Report Output

The test runner:

- prints results to the terminal
- saves the same output to a timestamped report file

Saved reports are written to:

- `project/tests/reports/`

Example report file:

- `project/tests/reports/unit_test_report_YYYYMMDD_HHMMSS.txt`

### Notes

- Some tests mock model behavior so the suite remains fast and deterministic.
- API tests require the project environment because they depend on FastAPI and related packages.
- The test report can be used as evaluation evidence in the final project report.

## Final Report Format

### Instructions

In this staff graded assignment you will submit your final project report. The report will consist of six chapters:

1. `Introduction`
   This will explain the project concept and motivation for the project, and must also state which project template is being used. Please include the project number in the way it has been listed in the template. Maximum 1000 words.

2. `Literature review`
   This is a revised version of the chapter from the draft report, to include any further work completed since then and to incorporate feedback obtained from previous submissions. Maximum 2500 words.

3. `Design`
   This is a revised version of the relevant chapter from the draft report, incorporating appropriate feedback and any design changes made based on feedback from previous submissions. Maximum 2000 words.

4. `Implementation`
   This should describe the implementation of the project. It should follow the style of the Topic 6 peer review, but be greatly expanded to cover the entire implementation. It should describe the major algorithms and techniques used, explain the most important parts of the code, and include a visual representation of the results such as screenshots or graphs. Maximum 2500 words.

5. `Evaluation`
   Describe the evaluation carried out, such as user studies or testing on data, and give the results. You should also justify your choices in the approach used to obtain and analyse the results. Your evaluation should critique the project as a whole, highlighting successes, failures, limitations, and possible extensions. Maximum 2500 words.

6. `Conclusion`
   This can be a short summary of the project as a whole, but it can also bring out broader themes you would like to discuss or suggest further work. Maximum 1000 words.

### Word Limit

- Total maximum: `10,500` words
- The total word count is a strict limit
- Each section limit is also strict
- Submissions that exceed the strict word limit will be penalised

In addition to the listed limits, you can have additional pages of images and references. The list of references, table and figure legends, and the titles of chapters are not included in the word limits.

### Submission Requirements

- Include a link to the code repository
- The repository must be publicly viewable at the time of submission
- The repository must remain viewable until results have been received
- You can return to previous peer reviews and the draft report instructions for guidance on the first four parts

### Video Requirement

As well as the report, you must submit a `3-5 minute` video demonstrating the project working.

The video should:

- Show the important features of the project
- Explain a little of how they work or justify the approaches taken
- Include appropriate visuals
- Contain spoken audio by you

The video must not:

- Use AI-generated voices
- Be speeded up
- Ignore the stated time and submission constraints

Videos that do not show a working project will receive significantly lower marks. Videos outside the stated constraints will be penalised.

## Final Report Review Criteria

- Is the report clearly written and presented?
- Are the diagrams and images appropriate and clear?
- Does the report display knowledge of the area of study, previous work and academic literature?
- Does the report critically evaluate the previous work and/or academic literature?
- Does the report use proper citation and referencing?
- Is the design of the project clear and of high quality?
- Is the project concept justified based on the domain and users?
- Is the final implementation of high quality, and is it described well?
- Is the final implementation technically challenging?
- Is the evaluation strategy appropriate to the aims of the project?
- Does the evaluation display good coverage of appropriate issues?
- Are the results of the evaluation presented well?
- Are the evaluation results used to critically analyse the project with respect to the aims and objectives of the project?
- Are there appropriate conclusions drawn, and is there appropriate concluding discussion?
- Is the overall quality of the discussion strong, with justification of claims and justification of decisions?
- Does the project display evidence of originality?
- Is there an appropriate video that demonstrates the working program, the achievements, and the understanding gained?
- Is the video well thought through, well structured, and impactful?

## Appendix References

### Nutrition and Data Sources

- Open Food Facts data portal: https://world.openfoodfacts.org/data
- FatSecret nutrition database: https://www.fatsecret.com/
- HealthifyMe nutrition database: https://www.healthifyme.com/

### Dish-Specific Reference

- Nasi lemak per 100 g reference: https://foods.fatsecret.com/calories-nutrition/generic/nasi-lemak%3Fportionamount%3D100.000%26frc%3DTrue%26portionid%3D6492921
- General nasi lemak entry: https://foods.fatsecret.com/calories-nutrition/generic/nasi-lemak

### Model References

- Food/non-food gate model: https://huggingface.co/prithivMLmods/Food-or-Not-SigLIP2
- Food classifier model: https://huggingface.co/Albertbeta123/resnet-50-chinese-food
- Semantic matching model: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- Diet advice model option: https://huggingface.co/google/flan-t5-base
- Alternative advice model option: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct

### Notes for Appendix Use

- `cai png` does not have one fixed macro profile because its nutrition depends on the rice portion and selected side dishes.
- Any macro entry used for `cai png` should be clearly described as an estimate rather than a fixed nutritional reference.
