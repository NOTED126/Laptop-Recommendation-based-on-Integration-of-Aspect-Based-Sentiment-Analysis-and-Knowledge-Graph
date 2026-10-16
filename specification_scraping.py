import os
import re
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException


def format_safe_filename(name: str) -> str:
    """Strips invalid file characters and standardizes spaces/hyphens to underscores."""
    cleaned = re.sub(r'[\\/*?:"<>|]', '', name)
    cleaned = re.sub(r'[\s-]+', '_', cleaned)
    return cleaned.strip('_')


def clean_price_to_float(raw_text: str) -> float | None:
    """Strips currency symbols and commas, converting raw price text into a float.

    Example: '$1,088.50' -> 1088.50
    """
    if not raw_text:
        return None
    match = re.search(r'[\d,]+(?:\.\d+)?', raw_text)
    if match:
        clean_num_str = match.group(0).replace(',', '')
        try:
            return float(clean_num_str)
        except ValueError:
            return None
    return None


class LaptopSpecScraper:
    def __init__(
        self,
        firefox_binary: str = r'C:\Program Files\Mozilla Firefox\firefox.exe',
        geckodriver_path: str = r'C:\Users\USER\Downloads\geckodriver-v0.36.0-win64\geckodriver.exe',
        output_folder: str = "./specifications/",
        desired_specs: list[str] | None = None
    ):
        self.firefox_binary = firefox_binary
        self.geckodriver_path = geckodriver_path
        self.output_folder = output_folder
        self.driver = None

        # Desired specs to extract
        self.desired_specs = desired_specs or [
            # General
            'Color',
            'Year of Release',
            # Display
            'Display Type',
            'Screen Type',
            'Screen Size',
            'Screen Resolution',
            'Touch Screen',
            'Refresh Rate',
            'Brightness',
            # CPU
            'Processor Brand',
            'Processor Model',
            'Processor Model Number',
            # Storage
            'Storage Type',
            'Total Storage Capacity',
            # Memory
            'System Memory (RAM)',
            'Type of Memory (RAM)',
            'System Memory RAM Speed',
            'Number Of Memory Slots',
            'Number of Memory Sticks Included',
            # GPU
            'Graphics Type',
            'GPU Brand',
            'Graphics',
            # Compatibility
            'Operating System',
            'Operating System Architecture',
            # Connectivity
            'Display Connector(s)',
            'Number of Thunderbolt Ports (Total)',
            'USB Ports',
            'Number of USB-C Charging Ports',
            'Headphone Jack',
            'Microphone Input',
            'Wireless Connectivity',
            'Wireless Networking Standard',
            'Number Of Ethernet Ports',
            # Cooling
            'CPU Cooling System',
            # Power
            'Power Supply Maximum Wattage',
            'Battery Life (up to)',
            # Camera
            'Front-Facing Camera',
            'Front Facing Camera Video Resolution',
            'Built-In Microphone',
            # Dimension
            'Product Height',
            'Product Width',
            'Product Depth',
            'Product Weight',
        ]

        # CSS and XPath Selectors
        self.css_price = "[data-testid='price-block-customer-price']"
        self.css_primary_image = "img.primary-image"
        self.css_specs_section = "[data-component-name='ProductSpecifications']"
        self.xpath_see_all_button = "//button[contains(., 'See all specifications')]"
        self.css_drawer_container = "[data-testid='brix-sheet-content']"
        self.css_spec_groups = "ul > li"

        # Ensure target folder exists
        os.makedirs(self.output_folder, exist_ok=True)

    def init_driver(self):
        """Initializes the Firefox WebDriver instance."""
        options = Options()
        options.binary_location = self.firefox_binary
        options.add_argument("--lang=en-US")

        self.driver = webdriver.Firefox(
            service=Service(self.geckodriver_path),
            options=options
        )
        self.driver.set_page_load_timeout(30)

    def extract_price(self) -> float | None:
        """Extracts and parses the price from the main product page."""
        try:
            price_elem = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.css_price))
            )
            try:
                raw_price = price_elem.find_element(By.CSS_SELECTOR, "span.sr-only").text.strip()
            except NoSuchElementException:
                raw_price = price_elem.text.strip()

            price_val = clean_price_to_float(raw_price)
            if price_val:
                print(f"Extracted Price: ${price_val}")
            else:
                print("Price not found/parsed.")
            return price_val
        except (TimeoutException, NoSuchElementException):
            print("Price element not found on page.")
            return None

    def extract_primary_image(self) -> str | None:
        """Extracts the product image source URL from the main page."""
        try:
            image_elem = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.css_primary_image))
            )
            image_url = image_elem.get_attribute("src")
            print(f"Extracted Image URL: {image_url}")
            return image_url
        except (TimeoutException, NoSuchElementException):
            print("Primary image element not found on page.")
            return None

    def open_specifications_drawer(self):
        """Scrolls to the specs section and opens the modal drawer."""
        try:
            print("Scrolling to Specifications section...")
            specs_section = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.css_specs_section))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", specs_section)
            time.sleep(2)

            print("Clicking 'See all specifications' button...")
            see_all_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, self.xpath_see_all_button))
            )
            self.driver.execute_script("arguments[0].click();", see_all_btn)
            print("Opened 'See all specifications' drawer.")
            time.sleep(3)
        except (TimeoutException, NoSuchElementException):
            print("Could not click 'See all specifications'. Checking if drawer is already active...")

    def parse_drawer_specifications(self, product_data: dict) -> dict:
        """Parses specification values from the open drawer container."""
        spec_container = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, self.css_drawer_container))
        )

        spec_groups = spec_container.find_elements(By.CSS_SELECTOR, self.css_spec_groups)

        for group in spec_groups:
            rows = group.find_elements(By.XPATH, "./div")

            for row in rows:
                try:
                    child_divs = row.find_elements(By.XPATH, "./div")
                    if len(child_divs) < 2:
                        continue

                    raw_label = child_divs[0].text.strip()
                    raw_value = child_divs[1].text.strip()

                    if raw_label and raw_value:
                        clean_label = raw_label.split('\n')[0].strip()
                        clean_value = raw_value.split('\n')[0].strip()

                        if clean_label in self.desired_specs:
                            product_data[clean_label] = clean_value

                except NoSuchElementException:
                    continue

        return product_data

    def scrape_laptop(self, laptop_info: dict) -> dict | None:
        """Processes a single laptop URL and exports its specifications CSV."""
        brand = laptop_info['brand']
        model = laptop_info['model']
        name = laptop_info['name']
        url = laptop_info['URL']

        print(f"\nProcessing [{brand} - {model}]: {name}")
        print(f"Opening URL: {url}")
        self.driver.get(url)
        time.sleep(5)  # Allow page and dynamic content to render

        price_val = self.extract_price()
        image_url = self.extract_primary_image()

        self.open_specifications_drawer()

        try:
            # Construct product metadata base (added Product URL)
            product_data = {
                'Brand': brand,
                'Model': model,
                'Product Name': name,
                'Product URL': url,
                'Price ($)': price_val,
                'Image URL': image_url
            }

            # Pre-initialize desired keys to None
            for key in self.desired_specs:
                product_data[key] = None

            product_data = self.parse_drawer_specifications(product_data)
            print(f"Successfully extracted specifications for {name}.")

            # Export to individual CSV
            self.save_product_csv(product_data)

            return product_data

        except TimeoutException:
            print(f"Failed to load specification container for {name}.")
            return None

    def save_product_csv(self, product_data: dict):
        """Saves individual product specification dict as a standardized CSV file."""
        df_single = pd.DataFrame([product_data])

        columns_order = ['Brand', 'Model', 'Product Name', 'Product URL', 'Price ($)', 'Image URL'] + self.desired_specs
        df_single = df_single.reindex(columns=columns_order)

        safe_filename = format_safe_filename(f"{product_data['Brand']}_{product_data['Model']}_specifications")
        output_file = os.path.join(self.output_folder, f"{safe_filename}.csv")

        df_single.to_csv(output_file, index=False)
        print(f"Saved individual CSV to: {output_file}")

    def scrape_all(self, laptops_list: list[dict]) -> list[dict]:
        """Iterates over a list of laptops and executes the extraction process."""
        all_specs = []
        for laptop in laptops_list:
            result = self.scrape_laptop(laptop)
            if result:
                all_specs.append(result)
        print("\nAll laptop extractions completed.")
        return all_specs

    def close(self):
        """Closes the Selenium browser driver."""
        if self.driver:
            self.driver.quit()
            print("Driver successfully closed.")

    # Context Manager Methods
    def __enter__(self):
        self.init_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Target dataset
LAPTOPS_TO_SCRAPE = [
    # Dell (7)
    {
        'brand': 'Dell',
        'model': '15.6 2K Touchscreen Laptop',
        'name': 'Dell 15.6 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-15-6-2k-touchscreen-laptop-intel-13th-generation-core-i7-1355u-2023-16gb-memory-512-gb-storage-carbon-black/J3K4L6QW5C/sku/6668952/openbox?condition=good'
    },
    {
        'brand': 'Dell',
        'model': 'Plus 16 2K 2-in-1 Touchscreen Laptop',
        'name': 'Dell Plus 16 2K 2-in-1 Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-plus-16-2k-2-in-1-touchscreen-laptop-intel-core-ultra-7-series-2-256v-2024-16gb-memory-1tb-storage-copilot-pc-ice-blue/J3K4L6XF7K'
    },
    {
        'brand': 'Dell',
        'model': 'XPS - 13.4 3K OLED Touchscreen Laptop',
        'name': 'Dell XPS - 13.4 3K OLED Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-xps-13-4-3k-oled-touchscreen-laptop-snapdragon-x-elite-x1e-80-2024-16gb-memory-512-gb-storage-copilot-pc-graphite/J3K4L6J9TG'
    },
    {
        'brand': 'Dell',
        'model': 'Inspiron - 15.6 2K Touchscreen Laptop',
        'name': 'Dell Inspiron - 15.6 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-inspiron-15-6-2k-touchscreen-laptop-amd-ryzen-7-7730u-2023-16gb-memory-1tb-storage-carbon-black/J3K4L6JRXP'
    },
    {
        'brand': 'Dell',
        'model': 'Plus - 16 2K Touchscreen Laptop',
        'name': 'Dell Plus - 16 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-plus-16-2k-touchscreen-laptop-amd-ryzen-ai-300-series-ai-7-350-2025-32gb-memory-1tb-storage-copilot-pc-ice-blue/J3K4L63SVF/sku/6628354'
    },
    {
        'brand': 'Dell',
        'model': 'Alienware - 16 Aurora 16 2.5K Gaming Laptop',
        'name': 'Dell Alienware - 16 Aurora 16 2.5K Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/alienware-16-aurora-16-2-5k-gaming-laptop-intel-core-7-series-2-240h-2024-32gb-memory-nvidia-geforce-rtx-5060-1tb-storage-interstellar-indigo/J3K4L6J65W'
    },
    {
        'brand': 'Dell',
        'model': 'Alienware - m16 R2 16 2.5K 240Hz Gaming Laptop',
        'name': 'Dell Alienware - m16 R2 16 2.5K 240Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/alienware-m16-r2-16-2-5k-240hz-gaming-laptop-intel-core-ultra-9-series-1-32gb-memory-nvidia-geforce-rtx-4070-1tb-storage-dark-metallic-moon/J3K4L626Y9'
    },

    # Acer (3)
    {
        'brand': 'Acer',
        'model': 'Swift Go 16 AI',
        'name': 'Acer Swift Go 16 AI',
        'URL': 'https://www.bestbuy.com/product/acer-swift-go-16-ai-copilot-pc-16-wuxga-touchscreen-laptop-amd-ryzen-ai-9-465-2026-32gb-memory-1tb-storage-obsidian-black/JJ8V8HLF6H'
    },
    {
        'brand': 'Acer',
        'model': 'Predator Helios Neo 16S AI Gaming Laptop',
        'name': 'Acer Predator Helios Neo 16S AI Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/acer-predator-helios-neo-16s-ai-gaming-laptop-16-oled-240hz-intel-core-ultra-9-nvidia-geforce-rtx-5070ti-32gb-1tb-obsidian-black/JJ8V8H38XT'
    },
    {
        'brand': 'Acer',
        'model': 'Chromebook 315 - 15.6 Full HD Laptop',
        'name': 'Acer Chromebook 315 - 15.6 Full HD Laptop',
        'URL': 'https://www.bestbuy.com/product/acer-chromebook-315-15-6-full-hd-laptop-intel-celeron-n4500-4gb-lpddr4x-64gb-emmc-protective-sleeve-silver/JJ8V8H3JC2'
    },

    # Lenovo (6)
    {
        'brand': 'Lenovo',
        'model': 'Legion 7i 16 2.5k OLED Gaming Laptop',
        'name': 'Lenovo Legion 7i 16 2.5k OLED Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-legion-7i-16-2-5k-oled-gaming-laptop-intel-core-ultra-9-275hx-2025-32gb-ram-nvidia-geforce-rtx-5070-1tb-ssd-glacier-white/JJGSH3Y5H9'
    },
    {
        'brand': 'Lenovo',
        'model': 'IdeaPad Slim 3i 15.6 Full HD Laptop',
        'name': 'Lenovo IdeaPad Slim 3i 15.6 Full HD Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-ideapad-slim-3i-15-6-full-hd-laptop-intel-processor-n355-2025-8gb-memory-128gb-storage-arctic-grey/JJGH3RGRLY'
    },
    {
        'brand': 'Lenovo',
        'model': 'IdeaPad Slim 3x - Copilot+ PC - 15.3 2k Touchscreen Laptop',
        'name': 'Lenovo IdeaPad Slim 3x - Copilot+ PC - 15.3 2k Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-ideapad-slim-3x-copilot-pc-15-3-2k-touchscreen-laptop-snapdragon-x-2025-16gb-memory-256gb-ssd-luna-grey/JJGSH82JL5/sku/6619147'
    },
    {
        'brand': 'Lenovo',
        'model': 'Yoga 7i 2-in-1 - Copilot+ PC - 16 2K Touchscreen Laptop',
        'name': 'Lenovo Yoga 7i 2-in-1 - Copilot+ PC - 16 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-yoga-7i-2-in-1-copilot-pc-16-2k-touchscreen-laptop-intel-core-ultra-5-processor-2024-16gb-memory-512gb-ssd-luna-grey/JJGSHC4F9F'
    },
    {
        'brand': 'Lenovo',
        'model': 'Legion Pro 5i 16 2.5k OLED Gaming Laptop',
        'name': 'Lenovo Legion Pro 5i 16 2.5k OLED Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-legion-pro-5i-16-2-5k-oled-gaming-laptop-intel-core-ultra-9-275hx-2025-32gb-ram-nvidia-geforce-rtx-5070-1tb-eclipse-black/JJGSHXJRCS'
    },
    {
        'brand': 'Lenovo',
        'model': 'LOQ 15.6 Full HD Gaming Laptop',
        'name': 'Lenovo LOQ 15.6 Full HD Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-loq-15-6-full-hd-gaming-laptop-amd-ryzen-5-7235hs-16gb-memory-nvidia-geforce-rtx-4050-512gb-ssd-luna-grey/JJGH3SKKHG'
    },

    # HP (6)
    {
        'brand': 'HP',
        'model': 'OmniBook X Flip 2-in-1 - 14 2K Touchscreen Laptop',
        'name': 'HP OmniBook X Flip 2-in-1 - 14 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-omnibook-x-flip-2-in-1-14-2k-touchscreen-laptop-intel-core-ultra-5-226v-2024-16gb-memory-512gb-ssd-copilot-atmospheric-blue/JJGQJRKGTJ'
    },
    {
        'brand': 'HP',
        'model': 'Victus 15.6 144Hz AMD Full HD Gaming Laptop',
        'name': 'HP Victus 15.6 144Hz AMD Full HD Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-victus-15-6-144hz-full-hd-gaming-laptop-amd-ryzen-7-7445hs-2023-16gb-memory-nvidia-geforce-rtx-4050-512gb-ssd-mica-silver/JJGH2L8JVV/sku/6623881'
    },
    {
        'brand': 'HP',
        'model': 'OmniBook 3 16 2K Touchscreen Laptop',
        'name': 'HP OmniBook 3 16 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-omnibook-3-16-2k-touchscreen-laptop-intel-core-ultra-7-2025-16gb-memory-512gb-ssd-mica-silver/J3YH84S23T'
    },
    {
        'brand': 'HP',
        'model': 'Victus 15.6 144Hz Intel Full HD Gaming Laptop',
        'name': 'HP Victus 15.6 144Hz Intel Full HD Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-victus-15-6-144hz-full-hd-gaming-laptop-intel-core-i5-13420h-2023-8gb-ram-nvidia-geforce-rtx-3050-512gb-ssd-mica-silver/JJGQJH2LFP/sku/6618924/openbox?condition=excellent'
    },
    {
        'brand': 'HP',
        'model': '15.6 Full HD Touch-Screen Laptop',
        'name': 'HP 15.6 Full HD Touch-Screen Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-15-6-full-hd-touch-screen-laptop-intel-core-i5-1334u-2023-16gb-memory-512gb-ssd-natural-silver/JJGH2YK5Q5'
    },
    {
        'brand': 'HP',
        'model': 'OMEN - MAX 16 OLED 240Hz Gaming Laptop',
        'name': 'HP OMEN - MAX 16 OLED 240Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-omen-max-16-oled-240hz-gaming-laptop-intel-core-ultra-9-275hx-2025-32gb-memory-nvidia-geforce-rtx-5080-2tb-ssd-shadow-black/JJGQJQXRTZ'
    },

    # ASUS (7)
    {
        'brand': 'ASUS',
        'model': 'ROG Zephyrus G14 14 3K OLED 120Hz Gaming Laptop',
        'name': 'ASUS ROG Zephyrus G14 14 3K OLED 120Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-rog-zephyrus-g14-14-3k-oled-120hz-gaming-laptop-amd-ryzen-9-270-16gb-memory-geforce-rtx-5060-1tb-storage-platinum-white/JJGGLH72GT'
    },
    {
        'brand': 'ASUS',
        'model': 'ROG Flow Z13 13.4 2.5K 180Hz Touch-Screen Gaming Laptop',
        'name': 'ASUS ROG Flow Z13 13.4 2.5K 180Hz Touch-Screen Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-rog-flow-z13-13-4-2-5k-180hz-touch-screen-gaming-laptop-copilot-pc-amd-ryzen-ai-max-395-64gb-memory-1tb-storage-off-black/JJGGLHG8X9'
    },
    {
        'brand': 'ASUS',
        'model': 'ROG Strix G16 16 FHD 165Hz Gaming Laptop',
        'name': 'ASUS ROG Strix G16 16 FHD 165Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-rog-strix-g16-16-fhd-165hz-gaming-laptop-amd-ryzen-9-8940hx-16gb-memory-geforce-rtx-5070-ti-1tb-storage-eclipse-gray/JJGGLHJLTS'
    },
    {
        'brand': 'ASUS',
        'model': 'Vivobook 16 16 FHD+ Laptop',
        'name': 'ASUS Vivobook 16 16 FHD+ Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-vivobook-16-16-fhd-laptop-amd-ryzen-7-7730u-with-16gb-memory-1tb-ssd-indie-black/JJGGLR7XFQ'
    },
    {
        'brand': 'ASUS',
        'model': 'Zenbook A14 14 2K OLED Laptop',
        'name': 'ASUS Zenbook A14 14 2K OLED Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-zenbook-a14-14-2k-oled-laptop-snapdragon-x-plus-2025-16gb-memory-512gb-storage-copilot-pc-zabriskie-beige/JJGGLH86J4/sku/6615728/openbox?condition=excellent'
    },
    {
        'brand': 'ASUS',
        'model': 'TUF Gaming F16 16 FHD+ 165Hz Gaming Laptop',
        'name': 'ASUS TUF Gaming F16 16 FHD+ 165Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-tuf-gaming-f16-16-fhd-165hz-gaming-laptop-intel-core-i7-14650hx-32gb-memory-geforce-rtx-5060-1tb-storage-jaeger-gray/JJGGLH8LZ5'
    },
    {
        'brand': 'ASUS',
        'model': 'ROG Strix G18 18 2.5K 240Hz Gaming Laptop',
        'name': 'ASUS ROG Strix G18 18 2.5K 240Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-rog-strix-g18-18-2-5k-240hz-gaming-laptop-intel-core-ultra-9-hx-32gb-memory-geforce-rtx-5080-2tb-storage-eclipse-gray/JJGGLHXFW8'
    },

    # MSI (1)
    {
        'brand': 'MSI',
        'model': 'THIN GF63 15.6 144Hz FHD Gaming Laptop',
        'name': 'MSI THIN GF63 15.6 144Hz FHD Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/msi-thin-gf63-15-6-144hz-fhd-gaming-laptop-intel-core-i5-12450h-with-8gb-memory-rtx-2050-1tb-ssd-black/J3P7TXYQVT'
    },
]


if __name__ == "__main__":
    # Runs scraper using context manager to ensure browser closes automatically
    with LaptopSpecScraper() as scraper:
        scraper.scrape_all(LAPTOPS_TO_SCRAPE)