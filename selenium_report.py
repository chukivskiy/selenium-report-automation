import csv
import logging
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


REPORT = Path(__file__).with_name("report.html").resolve()
OUTPUT = Path(__file__).with_name("output")


# 1. Context Manager for Selenium WebDriver
class WebDriverManager:
    def __init__(self):
        self.driver = None

    def __enter__(self):
        self.driver = webdriver.Chrome()
        self.driver.set_window_size(1400, 1100)
        return self.driver

    def __exit__(self, exc_type, exc_value, traceback):
        if self.driver is not None:
            self.driver.quit()
        return False


# 2. Save data to CSV
def save_csv(filename, header, rows):
    with (OUTPUT / filename).open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


# 3. Extract Plotly table and doughnut data
def get_plotly_data(driver):
    return driver.execute_script("""
        const gd = document.querySelector('.plotly-graph-div');

        const table = gd.data.find(
            trace => trace.type === 'table'
        );

        const pie = gd.data.find(
            trace => trace.type === 'pie'
        );

        const values = pie.values;
        let numericValues;

        if (Array.isArray(values) || ArrayBuffer.isView(values)) {
            numericValues = Array.from(values);

        } else if (values && values.bdata) {
            const binary = atob(values.bdata);

            const bytes = Uint8Array.from(
                binary,
                c => c.charCodeAt(0)
            );

            const view = new DataView(bytes.buffer);
            const little = !values.dtype.startsWith('>');
            const dtype = values.dtype.replace(/^[<>=|]/, '');
            const size = dtype.endsWith('8') ? 8 : 4;

            numericValues = [];

            for (let i = 0; i < bytes.length; i += size) {
                numericValues.push(
                    dtype.startsWith('f')
                        ? (
                            size === 8
                                ? view.getFloat64(i, little)
                                : view.getFloat32(i, little)
                        )
                        : (
                            size === 8
                                ? Number(view.getBigInt64(i, little))
                                : view.getInt32(i, little)
                        )
                );
            }

        } else {
            throw new Error('Unsupported Plotly pie values format');
        }

        return {
            headers: table.header.values,
            columns: table.cells.values,
            labels: pie.labels,
            values: numericValues,
            hidden: gd.layout.hiddenlabels || []
        };
    """)


# 4. Screenshot with fallback for zero-width chart
def save_chart_screenshot(driver, filename):
    screenshot_path = str(OUTPUT / filename)

    pie_layers = driver.find_elements(
        By.XPATH,
        "//*[local-name()='g' and contains(@class,'pielayer')]"
    )

    graphs = driver.find_elements(
        By.CLASS_NAME,
        "plotly-graph-div"
    )

    # First try the pie layer, then the Plotly container
    for element in pie_layers + graphs:
        try:
            size = element.size

            if size["width"] > 0 and size["height"] > 0:
                element.screenshot(screenshot_path)
                return

        except WebDriverException:
            continue

    # If no visible chart area exists, capture the viewport
    logging.warning(
        "Chart has zero width; saving browser screenshot instead"
    )

    driver.save_screenshot(screenshot_path)


# 5. Main workflow
def main():
    OUTPUT.mkdir(exist_ok=True)

    if not REPORT.is_file():
        raise FileNotFoundError(
            f"Report not found: {REPORT}"
        )

    with WebDriverManager() as driver:
        driver.get(REPORT.as_uri())

        wait = WebDriverWait(driver, 20)

        # Locator 1: CLASS_NAME
        graph = wait.until(
            lambda d: d.find_element(
                By.CLASS_NAME,
                "plotly-graph-div"
            )
        )

        # Locator 2: CSS_SELECTOR
        wait.until(
            lambda d: d.find_element(
                By.CSS_SELECTOR,
                ".plotly-graph-div svg.main-svg"
            )
        )

        # Locator 3: XPATH
        wait.until(
            lambda d: d.find_element(
                By.XPATH,
                "//*[local-name()='g' and contains(@class,'pielayer')]"
            )
        )

        # Wait for Plotly data to load
        wait.until(
            lambda d: d.execute_script(
                "return !!(arguments[0].data && "
                "arguments[0].data.length >= 2)",
                graph
            )
        )

        # -----------------------------
        # TABLE EXPORT
        # -----------------------------
        data = get_plotly_data(driver)

        rows = list(zip(*data["columns"]))

        save_csv(
            "table.csv",
            data["headers"],
            rows
        )

        logging.info(
            "Saved table.csv: %d rows",
            len(rows)
        )

        # -----------------------------
        # INITIAL DOUGHNUT CHART
        # -----------------------------
        save_chart_screenshot(
            driver,
            "screenshot0.png"
        )

        save_csv(
            "doughnut0.csv",
            ["Facility Type", "Min Average Time Spent"],
            zip(data["labels"], data["values"])
        )

        # -----------------------------
        # FILTER INTERACTION
        # -----------------------------
        legend_items = driver.find_elements(
            By.CSS_SELECTOR,
            ".legend .traces"
        )

        if not legend_items:
            logging.warning(
                "No interactive pie legend detected"
            )
            return

        for index in range(len(legend_items)):
            try:
                old_hidden = set(
                    get_plotly_data(driver)["hidden"]
                )

                # Re-find elements after Plotly re-rendering
                items = driver.find_elements(
                    By.CSS_SELECTOR,
                    ".legend .traces"
                )

                label = items[index].text.strip()

                items[index].click()

                # Wait until the filter changes
                wait.until(
                    lambda d: set(
                        get_plotly_data(d)["hidden"]
                    ) != old_hidden
                )

                # Save screenshot
                save_chart_screenshot(
                    driver,
                    f"screenshot{index + 1}.png"
                )

                # Extract filtered data
                state = get_plotly_data(driver)
                hidden = set(state["hidden"])

                filtered_rows = [
                    (name, value)
                    for name, value in zip(
                        state["labels"],
                        state["values"]
                    )
                    if name not in hidden
                ]

                # Save filtered CSV
                save_csv(
                    f"doughnut{index + 1}.csv",
                    ["Facility Type", "Min Average Time Spent"],
                    filtered_rows
                )

                logging.info(
                    "Filter %s -> %d remaining categories",
                    label,
                    len(filtered_rows)
                )

            except (
                TimeoutException,
                WebDriverException,
                ValueError
            ) as exc:
                logging.error(
                    "Could not process legend filter %d: %s",
                    index,
                    exc
                )
                break


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    main()
