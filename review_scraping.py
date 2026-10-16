import os
import re
import time
import random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException


def format_safe_filename(name: str) -> str:
    """Strips invalid file system characters and replaces spaces/hyphens with underscores."""
    cleaned = re.sub(r'[\\/*?:"<>|]', '', name)
    cleaned = re.sub(r'[\s-]+', '_', cleaned)
    return cleaned.strip('_')


def modify_link(url: str) -> str:
    """Transforms a standard product URL into the paginated review listing URL format."""
    text = url.replace("/product/", "/site/reviews/")
    text = re.sub(r"/[^/]+/sku/", "/", text)
    text = re.sub(r"/reviews$", "?variant=A&sort=NEWEST&page=", text)
    return text


class BestBuyReviewScraper:
    def __init__(
        self,
        firefox_binary: str = r'C:\Program Files\Mozilla Firefox\firefox.exe',
        geckodriver_path: str = r'C:\Users\USER\Downloads\geckodriver-v0.36.0-win64\geckodriver.exe',
        output_folder: str = "./reviews/",
        max_reviews_per_product: int = 200
    ):
        self.firefox_binary = firefox_binary
        self.geckodriver_path = geckodriver_path
        self.output_folder = output_folder
        self.max_reviews_per_product = max_reviews_per_product
        self.driver = None

        # CSS Selectors
        self.css_path_reviews = "[class='w-full py-200']"
        self.css_path_review_text = "[class='relative'] > p"
        self.css_path_review_date = "[class='disclaimer mt-300 mb-none text-3'] > [class='text-2'] > time"

        os.makedirs(self.output_folder, exist_ok=True)

    def init_driver(self):
        """Initializes a new Firefox WebDriver instance."""
        options = Options()
        options.binary_location = self.firefox_binary
        options.add_argument("--lang=en-US")

        self.driver = webdriver.Firefox(
            service=Service(self.geckodriver_path),
            options=options
        )
        self.driver.set_page_load_timeout(30)

    def close_driver(self):
        """Safely terminates the active browser driver."""
        if self.driver:
            try:
                self.driver.quit()
                print("Browser closed.")
            except Exception as e:
                print(f"Error while closing driver: {e}")
            finally:
                self.driver = None

    def scrape_product_reviews(self, product_name: str, info: dict) -> list[dict]:
        """Scrapes review entries across pages for a single product."""
        self.init_driver()
        reviews_list = []
        review_count = 0

        base_url = modify_link(info['URL'])
        max_pages = info.get('URL_pages', 11)
        brand = info['brand']
        model = info['model']

        try:
            for page in range(1, max_pages + 1):
                if review_count >= self.max_reviews_per_product:
                    break

                print(f"Opening page {page}...")
                self.driver.get(f"{base_url}{page}")

                # Random sleep interval to mimic human behavior
                time.sleep(random.randint(5, 10))

                try:
                    review_elements = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, self.css_path_reviews))
                    )
                except TimeoutException:
                    print("No reviews found on this page.")
                    continue

                for elem in review_elements:
                    if review_count >= self.max_reviews_per_product:
                        break

                    print(f"Extracting review {review_count + 1}...")

                    # Extract text content
                    try:
                        text = elem.find_element(By.CSS_SELECTOR, self.css_path_review_text).text
                    except NoSuchElementException:
                        text = "No text found"

                    # Extract posted date title attribute
                    try:
                        date_elem = elem.find_element(By.CSS_SELECTOR, self.css_path_review_date)
                        date = date_elem.get_attribute("title")
                    except NoSuchElementException:
                        date = None

                    reviews_list.append({
                        'Review Count': review_count + 1,
                        'Brand': brand,
                        'Model': model,
                        'Product': product_name,
                        'Date': date,
                        'Review': text
                    })

                    review_count += 1

            print(f"Finished {product_name} with {review_count} reviews.")

        finally:
            self.close_driver()

        return reviews_list

    def save_reviews_csv(self, product_name: str, reviews_list: list[dict]):
        """Saves a product's scraped reviews to an individual CSV file."""
        if not reviews_list:
            print(f"No reviews to save for {product_name}.")
            return

        safe_filename = format_safe_filename(f"{product_name}_reviews")
        file_path = os.path.join(self.output_folder, f"{safe_filename}.csv")

        df = pd.DataFrame(reviews_list)
        df.to_csv(file_path, index=False)
        print(f"Saved to {file_path}")

    def scrape_all(self, product_dict: dict):
        """Iterates over all defined products, extracting and saving reviews."""
        total_products = len(product_dict)

        for counter, (product_name, info) in enumerate(product_dict.items(), start=1):
            print(f"\nStart scraping for product: {product_name}")

            reviews = self.scrape_product_reviews(product_name, info)
            self.save_reviews_csv(product_name, reviews)

            if counter == total_products:
                print("\nFinished extracting ALL product reviews!")
            else:
                # Politeness delay logic between product requests
                wait_time = 30 if counter % 5 == 0 else random.randint(5, 10)
                print(f"Waiting {wait_time} seconds before next product...\n")
                time.sleep(wait_time)


# Target dataset configuration
PRODUCT_DICT = {
    # Dell (7)
    'Dell 15.6 2K Touchscreen Laptop':
    {
        'brand': 'Dell',
        'model': '15.6 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-15-6-2k-touchscreen-laptop-intel-13th-generation-core-i7-1355u-2023-16gb-memory-512-gb-storage-carbon-black/J3K4L6QW5C/sku/6668952/reviews',
        'URL_pages': 11
    },
    'Dell Plus 16 2K 2-in-1 Touchscreen Laptop':
    {
        'brand': 'Dell',
        'model': 'Plus 16 2K 2-in-1 Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-plus-16-2k-2-in-1-touchscreen-laptop-intel-core-ultra-7-series-2-256v-2024-16gb-memory-1tb-storage-copilot-pc-ice-blue/J3K4L6XF7K/sku/10936948/reviews',
        'URL_pages': 11
    },
    'Dell XPS - 13.4 3K OLED Touchscreen Laptop':
    {
        'brand': 'Dell',
        'model': 'XPS - 13.4 3K OLED Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-xps-13-4-3k-oled-touchscreen-laptop-snapdragon-x-elite-x1e-80-2024-16gb-memory-512-gb-storage-copilot-pc-graphite/J3K4L6J9TG/sku/12634079/reviews',
        'URL_pages': 11
    },
    'Dell Inspiron - 15.6 2K Touchscreen Laptop':
    {
        'brand': 'Dell',
        'model': 'Inspiron - 15.6 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-inspiron-15-6-2k-touchscreen-laptop-amd-ryzen-7-7730u-2023-16gb-memory-1tb-storage-carbon-black/J3K4L6JRXP/sku/11034179/reviews',
        'URL_pages': 11
    },
    'Dell Plus - 16 2K Touchscreen Laptop':
    {
        'brand': 'Dell',
        'model': 'Plus - 16 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/dell-plus-16-2k-touchscreen-laptop-amd-ryzen-ai-300-series-ai-7-350-2025-32gb-memory-1tb-storage-copilot-pc-ice-blue/J3K4L63SVF/sku/6628354/reviews',
        'URL_pages': 11
    },
    'Dell Alienware - 16 Aurora 16 2.5K Gaming Laptop':
    {
        'brand': 'Dell',
        'model': 'Alienware - 16 Aurora 16 2.5K Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/alienware-16-aurora-16-2-5k-gaming-laptop-intel-core-7-series-2-240h-2024-32gb-memory-nvidia-geforce-rtx-5060-1tb-storage-interstellar-indigo/J3K4L6J65W/sku/11747633/reviews',
        'URL_pages': 11
    },
    'Dell Alienware - m16 R2 16 2.5K 240Hz Gaming Laptop':
    {
        'brand': 'Dell',
        'model': 'Alienware - m16 R2 16 2.5K 240Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/alienware-m16-r2-16-2-5k-240hz-gaming-laptop-intel-core-ultra-9-series-1-32gb-memory-nvidia-geforce-rtx-4070-1tb-storage-dark-metallic-moon/J3K4L626Y9/sku/6576922/reviews',
        'URL_pages': 11
    },

    # Acer (3)
    'Acer Swift Go 16 AI':
    {
        'brand': 'Acer',
        'model': 'Swift Go 16 AI',
        'URL': 'https://www.bestbuy.com/product/acer-swift-go-16-ai-copilot-pc-16-wuxga-touchscreen-laptop-amd-ryzen-ai-9-465-2026-32gb-memory-1tb-storage-obsidian-black/JJ8V8HLF6H/sku/12681807/reviews',
        'URL_pages': 11
    },
    'Acer Predator Helios Neo 16S AI Gaming Laptop':
    {
        'brand': 'Acer',
        'model': 'Predator Helios Neo 16S AI Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/acer-predator-helios-neo-16s-ai-gaming-laptop-16-oled-240hz-intel-core-ultra-9-nvidia-geforce-rtx-5070ti-32gb-1tb-obsidian-black/JJ8V8H38XT/sku/6619312/reviews',
        'URL_pages': 11
    },
    'Acer Chromebook 315 - 15.6 Full HD Laptop':
    {
        'brand': 'Acer',
        'model': 'Chromebook 315 - 15.6 Full HD Laptop',
        'URL': 'https://www.bestbuy.com/product/acer-chromebook-315-15-6-full-hd-laptop-intel-celeron-n4500-4gb-lpddr4x-64gb-emmc-protective-sleeve-silver/JJ8V8H3JC2/sku/12657340/reviews',
        'URL_pages': 11
    },

    # Lenovo (6)
    'Lenovo Legion 7i 16 2.5k OLED Gaming Laptop':
    {
        'brand': 'Lenovo',
        'model': 'Legion 7i 16 2.5k OLED Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-legion-7i-16-2-5k-oled-gaming-laptop-intel-core-ultra-9-275hx-2025-32gb-ram-nvidia-geforce-rtx-5070-1tb-ssd-glacier-white/JJGSH3Y5H9/sku/12672667/reviews',
        'URL_pages': 11
    },
    'Lenovo IdeaPad Slim 3i 15.6 Full HD Laptop':
    {
        'brand': 'Lenovo',
        'model': 'IdeaPad Slim 3i 15.6 Full HD Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-ideapad-slim-3i-15-6-full-hd-laptop-intel-processor-n355-2025-8gb-memory-128gb-storage-arctic-grey/JJGH3RGRLY/sku/13015868/reviews',
        'URL_pages': 11
    },
    'Lenovo IdeaPad Slim 3x - Copilot+ PC - 15.3 2k Touchscreen Laptop':
    {
        'brand': 'Lenovo',
        'model': 'IdeaPad Slim 3x - Copilot+ PC - 15.3 2k Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-ideapad-slim-3x-copilot-pc-15-3-2k-touchscreen-laptop-snapdragon-x-2025-16gb-memory-256gb-ssd-luna-grey/JJGSH82JL5/sku/6619147/reviews',
        'URL_pages': 11
    },
    'Lenovo Yoga 7i 2-in-1 - Copilot+ PC - 16 2K Touchscreen Laptop':
    {
        'brand': 'Lenovo',
        'model': 'Yoga 7i 2-in-1 - Copilot+ PC - 16 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-yoga-7i-2-in-1-copilot-pc-16-2k-touchscreen-laptop-intel-core-ultra-5-processor-2024-16gb-memory-512gb-ssd-luna-grey/JJGSHC4F9F/sku/10947502/reviews',
        'URL_pages': 11
    },
    'Lenovo Legion Pro 5i 16 2.5k OLED Gaming Laptop':
    {
        'brand': 'Lenovo',
        'model': 'Legion Pro 5i 16 2.5k OLED Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-legion-pro-5i-16-2-5k-oled-gaming-laptop-intel-core-ultra-9-275hx-2025-32gb-ram-nvidia-geforce-rtx-5070-1tb-eclipse-black/JJGSHXJRCS/sku/12349134/reviews',
        'URL_pages': 11
    },
    'Lenovo LOQ 15.6 Full HD Gaming Laptop':
    {
        'brand': 'Lenovo',
        'model': 'LOQ 15.6 Full HD Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/lenovo-loq-15-6-full-hd-gaming-laptop-amd-ryzen-5-7235hs-16gb-memory-nvidia-geforce-rtx-4050-512gb-ssd-luna-grey/JJGH3SKKHG/sku/6646505/reviews',
        'URL_pages': 11
    },

    # HP (6)
    'HP OmniBook X Flip 2-in-1 - 14 2K Touchscreen Laptop':
    {
        'brand': 'HP',
        'model': 'OmniBook X Flip 2-in-1 - 14 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-omnibook-x-flip-2-in-1-14-2k-touchscreen-laptop-intel-core-ultra-5-226v-2024-16gb-memory-512gb-ssd-copilot-atmospheric-blue/JJGQJRKGTJ/sku/6613868/reviews',
        'URL_pages': 11
    },
    'HP Victus 15.6 144Hz AMD Full HD Gaming Laptop':
    {
        'brand': 'HP',
        'model': 'Victus 15.6 144Hz AMD Full HD Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-victus-15-6-144hz-full-hd-gaming-laptop-amd-ryzen-7-7445hs-2023-16gb-memory-nvidia-geforce-rtx-4050-512gb-ssd-mica-silver/JJGH2L8JVV/sku/6623881/reviews',
        'URL_pages': 11
    },
    'HP OmniBook 3 16 2K Touchscreen Laptop':
    {
        'brand': 'HP',
        'model': 'OmniBook 3 16 2K Touchscreen Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-omnibook-3-16-2k-touchscreen-laptop-intel-core-ultra-7-2025-16gb-memory-512gb-ssd-mica-silver/J3YH84S23T/sku/6672898/reviews',
        'URL_pages': 11
    },
    'HP Victus 15.6 144Hz Intel Full HD Gaming Laptop':
    {
        'brand': 'HP',
        'model': 'Victus 15.6 144Hz Intel Full HD Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-victus-15-6-144hz-full-hd-gaming-laptop-intel-core-i5-13420h-2023-8gb-ram-nvidia-geforce-rtx-3050-512gb-ssd-mica-silver/JJGQJH2LFP/sku/6618924/reviews',
        'URL_pages': 11
    },
    'HP 15.6 Full HD Touch-Screen Laptop':
    {
        'brand': 'HP',
        'model': '15.6 Full HD Touch-Screen Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-15-6-full-hd-touch-screen-laptop-intel-core-i5-1334u-2023-16gb-memory-512gb-ssd-natural-silver/JJGH2YK5Q5/sku/11401115/reviews',
        'URL_pages': 11
    },
    'HP OMEN - MAX 16 OLED 240Hz Gaming Laptop':
    {
        'brand': 'HP',
        'model': 'OMEN - MAX 16 OLED 240Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/hp-omen-max-16-oled-240hz-gaming-laptop-intel-core-ultra-9-275hx-2025-32gb-memory-nvidia-geforce-rtx-5080-2tb-ssd-shadow-black/JJGQJQXRTZ/sku/6615951/reviews',
        'URL_pages': 11
    },

    # ASUS (7)
    'ASUS ROG Zephyrus G14 14 3K OLED 120Hz Gaming Laptop':
    {
        'brand': 'ASUS',
        'model': 'ROG Zephyrus G14 14 3K OLED 120Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-rog-zephyrus-g14-14-3k-oled-120hz-gaming-laptop-amd-ryzen-9-270-16gb-memory-geforce-rtx-5060-1tb-storage-platinum-white/JJGGLH72GT/sku/6629420/reviews',
        'URL_pages': 11
    },
    'ASUS ROG Flow Z13 13.4 2.5K 180Hz Touch-Screen Gaming Laptop':
    {
        'brand': 'ASUS',
        'model': 'ROG Flow Z13 13.4 2.5K 180Hz Touch-Screen Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-rog-flow-z13-13-4-2-5k-180hz-touch-screen-gaming-laptop-copilot-pc-amd-ryzen-ai-max-395-64gb-memory-1tb-storage-off-black/JJGGLHG8X9/sku/6619196/reviews',
        'URL_pages': 11
    },
    'ASUS ROG Strix G16 16 FHD 165Hz Gaming Laptop':
    {
        'brand': 'ASUS',
        'model': 'ROG Strix G16 16 FHD 165Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-rog-strix-g16-16-fhd-165hz-gaming-laptop-amd-ryzen-9-8940hx-16gb-memory-geforce-rtx-5070-ti-1tb-storage-eclipse-gray/JJGGLHJLTS/sku/6613956/reviews',
        'URL_pages': 11
    },
    'ASUS Vivobook 16 16 FHD+ Laptop':
    {
        'brand': 'ASUS',
        'model': 'Vivobook 16 16 FHD+ Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-vivobook-16-16-fhd-laptop-amd-ryzen-7-7730u-with-16gb-memory-1tb-ssd-indie-black/JJGGLR7XFQ/sku/12791144/reviews',
        'URL_pages': 11
    },
    'ASUS Zenbook A14 14 2K OLED Laptop':
    {
        'brand': 'ASUS',
        'model': 'Zenbook A14 14 2K OLED Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-zenbook-a14-14-2k-oled-laptop-snapdragon-x-plus-2025-16gb-memory-512gb-storage-copilot-pc-zabriskie-beige/JJGGLH86J4/sku/6615728/reviews',
        'URL_pages': 11
    },
    'ASUS TUF Gaming F16 16 FHD+ 165Hz Gaming Laptop':
    {
        'brand': 'ASUS',
        'model': 'TUF Gaming F16 16 FHD+ 165Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-tuf-gaming-f16-16-fhd-165hz-gaming-laptop-intel-core-i7-14650hx-32gb-memory-geforce-rtx-5060-1tb-storage-jaeger-gray/JJGGLH8LZ5/sku/6629421/reviews',
        'URL_pages': 11
    },
    'ASUS ROG Strix G18 18 2.5K 240Hz Gaming Laptop':
    {
        'brand': 'ASUS',
        'model': 'ROG Strix G18 18 2.5K 240Hz Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/asus-rog-strix-g18-18-2-5k-240hz-gaming-laptop-intel-core-ultra-9-hx-32gb-memory-geforce-rtx-5080-2tb-storage-eclipse-gray/JJGGLHXFW8/sku/6613958/reviews',
        'URL_pages': 11
    },

    # MSI (1)
    'MSI THIN GF63 15.6 144Hz FHD Gaming Laptop':
    {
        'brand': 'MSI',
        'model': 'THIN GF63 15.6 144Hz FHD Gaming Laptop',
        'URL': 'https://www.bestbuy.com/product/msi-thin-gf63-15-6-144hz-fhd-gaming-laptop-intel-core-i5-12450h-with-8gb-memory-rtx-2050-1tb-ssd-black/J3P7TXYQVT/sku/13085790/reviews',
        'URL_pages': 11
    },
}


def main():
    scraper = BestBuyReviewScraper()
    scraper.scrape_all(PRODUCT_DICT)


if __name__ == "__main__":
    main()