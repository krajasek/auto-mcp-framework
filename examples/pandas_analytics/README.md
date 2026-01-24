# Pandas Analytics Example

Demonstrates creating an MCP server for pandas data analysis using a manifest file for selective tool exposure.

## Files

- `manifest.yaml` - YAML manifest defining which pandas functions to expose
- `server.py` - Generated MCP server (created from manifest)
- `run_server.py` - Helper script to run the server

## Prerequisites

```bash
pip install pandas
```

## User Workflow

### Step 1: Create a Manifest

The `manifest.yaml` file selects which pandas functions to expose (97 tools from 500+):

```yaml
server_name: pandas-mcp-server
auto_include_dependencies: true

tools:
  # Data reading
  - function: read_csv
    description: "Read a CSV file into a DataFrame."

  # DataFrame operations
  - function: DataFrame.head
    name: dataframe_head
    description: "Return the first n rows."

  - function: DataFrame.groupby
    name: dataframe_groupby
    description: "Group DataFrame by columns."
  # ... more tools
```

### Step 2: Generate the Server

```bash
auto-mcp-tool generate pandas --manifest manifest.yaml -o server.py
```

### Step 3: Run the Server

```bash
python server.py
```

Or use the helper script:

```bash
python run_server.py
```

## Claude Desktop Integration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pandas": {
      "command": "python",
      "args": ["/path/to/examples/pandas_analytics/server.py"]
    }
  }
}
```

## Available Tools (97 total)

### Data Reading
- `read_csv`, `read_excel`, `read_json`, `read_parquet`, `read_sql`, `read_html`, `read_clipboard`

### DataFrame Viewing
- `dataframe_head`, `dataframe_tail`, `dataframe_info`, `dataframe_describe`
- `dataframe_shape`, `dataframe_dtypes`, `dataframe_columns`, `dataframe_index`

### Selection & Indexing
- `dataframe_loc`, `dataframe_iloc`, `dataframe_at`, `dataframe_iat`
- `dataframe_query`, `dataframe_filter`, `dataframe_sample`
- `dataframe_nlargest`, `dataframe_nsmallest`

### Data Cleaning
- `dataframe_dropna`, `dataframe_fillna`, `dataframe_isna`, `dataframe_notna`
- `dataframe_drop_duplicates`, `dataframe_duplicated`
- `dataframe_replace`, `dataframe_rename`, `dataframe_astype`

### Transformation
- `dataframe_apply`, `dataframe_transform`, `dataframe_assign`
- `dataframe_drop`, `dataframe_set_index`, `dataframe_reset_index`
- `dataframe_sort_values`, `dataframe_sort_index`

### Grouping & Aggregation
- `dataframe_groupby`, `dataframe_agg`, `dataframe_pivot`, `dataframe_pivot_table`
- `dataframe_melt`, `dataframe_stack`, `dataframe_unstack`

### Merging & Joining
- `dataframe_merge`, `dataframe_join`, `dataframe_concat`

### Statistics
- `dataframe_sum`, `dataframe_mean`, `dataframe_median`, `dataframe_std`
- `dataframe_min`, `dataframe_max`, `dataframe_count`, `dataframe_corr`

### Export
- `dataframe_to_csv`, `dataframe_to_excel`, `dataframe_to_json`
- `dataframe_to_parquet`, `dataframe_to_dict`, `dataframe_to_markdown`

## How Handle-Based Storage Works

DataFrames are stored in memory and referenced by handles:

```python
# Reading returns a handle
df = read_csv("data.csv")  # Returns "DataFrame_1"

# Operations use handles
result = dataframe_head(df, n=5)  # Returns actual row data

# Transformations return new handles
filtered = dataframe_query(df, "age > 30")  # Returns "DataFrame_2"
```

## Example Interactions

```
User: Read sales.csv and show the first 5 rows
Assistant: [calls read_csv("sales.csv")]
-> "DataFrame_1"
Assistant: [calls dataframe_head("DataFrame_1", 5)]
-> | product | quantity | price |
   | Widget  | 100      | 9.99  |
   | Gadget  | 50       | 19.99 |
   ...

User: What are the descriptive statistics?
Assistant: [calls dataframe_describe("DataFrame_1")]
-> count, mean, std, min, max for numeric columns

User: Group by product and sum quantities
Assistant: [calls dataframe_groupby("DataFrame_1", "product")]
-> "DataFrameGroupBy_1"
Assistant: [calls dataframe_agg("DataFrameGroupBy_1", {"quantity": "sum"})]
-> | product | quantity |
   | Widget  | 500      |
   | Gadget  | 200      |

User: Save to output.csv
Assistant: [calls dataframe_to_csv("DataFrame_1", "output.csv")]
-> Saved successfully
```

## Why Use a Manifest?

Pandas has 500+ functions. The manifest allows you to:
- **Select relevant tools** - Only expose what users need
- **Custom descriptions** - Provide clear, concise descriptions
- **Faster loading** - Smaller server with fewer tools
- **Better LLM performance** - Fewer tool choices = better selection

## Regenerating the Server

After modifying `manifest.yaml`:

```bash
auto-mcp-tool generate pandas --manifest manifest.yaml -o server.py
```

## Deployment Notes

The handle-based storage requires a **single-process server**. See the main README's "Deployment Considerations for Handle-Based Storage" section.
