import re
import time
import selenium.common.exceptions as sce
from selenium.webdriver.common.action_chains import ActionChains

from uiautomationtools.logging.logger import Logger
from uiautomationtools.helpers.list_helpers import unique_subsets


class SeleniumAppiumShared(object):
    """
    This class contains methods that can be shared between selenium and appium. At runtime this class
    expects to have the context of some selenium driver.
    """

    def __init__(self):
        """
        The constructor for SeleniumAppiumShared.
        """
        if not getattr(self, 'logging', None):
            self.logging = Logger()
            self.logger = self.logging.logger

        self.driver_exceptions = sce
        self.time = time
        self.action_chains = ActionChains
        self.find_element_time = []

        self.platform_name = self.capabilities.get('platformName')
        if self.platform_name in ['android', 'ios']:
            self.platform_name = self.platform_name.lower()
        else:
            self.platform_name = self.capabilities['browserName'].lower()

        self._active_element = None

    def click_override(self, native=False):
        """
        This will override the .click method for web apps and views.

        Args:
            native (bool): Whether to force the native click action.
        """
        self.time.sleep(.5)
        context = getattr(self, 'current_context', 'None').lower()
        if native or 'native' in context:
            self._active_element._execute('clickElement')
        else:
            self.execute_script('arguments[0].click();', self._active_element)

    def find_element_explicitly(self, value, by='xpath', timeout=15, safe=False, many=False, class_conversion=True):
        """
        This wraps .find_element with an explicit timeout sleep and search.

        Args:
            value (str): The element search string.
            by (str): The method for applying the search string.
            timeout (int): The search duration for an element before raising an error.
            safe (bool): Whether to catch errors on elements not found.
            many (bool): Whether to find multiple elements.
            class_conversion(bool): It will convert Android classname to iOS calssname & vice versa.

        Returns:
            element (WebElement): The found element.
        """
        if self.platform_name == 'ios' and by == 'xpath':
            value = value.split('=')[-1][1:-2]
            by = 'id'

        error = None

        if not class_conversion:
          val = self.special_cases(value)
        else:
          val = self.path_conversion(value)

        timeout_ms = self.time.time() + timeout
        while self.time.time() <= timeout_ms:
            try:
                if not many:
                    element = self.find_element(by, val)
                    if self.platform_name in 'ios':
                      element.get_attribute('type')
                    else:
                        element.get_attribute('class')

                    if not element.is_displayed() or not element.is_enabled():
                        raise self.driver_exceptions.NoSuchElementException()

                    # WORKAROUND - overriding .click
                    self._active_element = element
                    self._active_element.click = self.click_override
                else:
                    element = self.find_elements(by, val)
                    if not element:
                        raise self.driver_exceptions.NoSuchElementException()

                    if val != 'body':
                        if 'native' not in self.context.lower():
                            if self.platform_name in 'ios':
                                 element = self.execute_script("return arguments[0].filter(e => e.getAttribute('type'));", element)
                            else:
                                 element = self.execute_script("return arguments[0].filter(e => e.getAttribute('class'));", element)

                        else:
                            # TODO - make async
                            if self.platform_name in 'ios':
                                element = [ele for ele in element if ele.get_attribute('type')]
                            else:
                                element = [ele for ele in element if ele.get_attribute('class')]

                self.find_element_time.append([val, timeout - (timeout_ms - self.time.time())])
                return element
            except (self.driver_exceptions.NoSuchElementException,
                    self.driver_exceptions.StaleElementReferenceException) as e:
                self.find_element_time.append([val, timeout - (timeout_ms - self.time.time())])
                self.time.sleep(.15)
                error = e

        if not safe:
            self.logger.error('\n')
            error_message = f'Unable to find the {by}: {val} within {timeout} seconds.'
            self.logger.error(f'{error_message}\n')
            raise (eval(f'self.driver_exceptions.{error.__class__.__name__}')(error_message))

        return None

    def get_page_source(self, value='div', by='css selector', timeout=15, safe=False):
        """
        This looks for the div containing the most information then does a .innerHtml on it.

        Args:
            value (str): The element search string.
            by (str): The method for applying the search string.
            timeout (int): The max time to check for a page change.
            safe (bool): Whether to raise errors on no new page source found.

        Returns:
            page_source (str): The inner html of the fattest div on the page.
        """
        elements = self.find_element_explicitly(value, by, many=True, safe=True, timeout=timeout)
        if elements:
            js_code = "return arguments[0].filter(e => e.innerText).map(e => [e.innerText, e.innerHTML]);"
            elements = self.execute_script(js_code, elements)

        elements = [[[t.strip() for t in re.split(r'\n+', e[0]) if t.strip()], e[1]] for e in elements]
        elements = [e for e in elements if len(e[0]) > 0]

        text = [e[0] for e in elements]
        unique_text = list(dict.fromkeys([t2 for t1 in text for t2 in t1 if t2]))
        if ''.join(unique_text):
                all_encompassing, unique_text = unique_subsets(text, unique_text)

                # TODO - need a better way to decide on data and grab leftovers
                if unique_text:
                    leftovers = [subset for subset in text if set(unique_text) <= set(subset)]
                    not leftovers or all_encompassing.append(leftovers[0])

                sources = [elements[i][1] for i in [text.index(a) for a in all_encompassing]]
                return ''.join(sources)

        if not safe:
            self.logger.error('\n')
            error_message = f'Unable to find the page source within {timeout} seconds.'
            self.logger.error(f'{error_message}\n')
            raise self.driver_exceptions.NoSuchElementException(error_message)
        return {}

    def get_element_screenshot(self, element, path):
        """
        This captures screenshot of specific webelement and writes it to a specific location.

        Args:
            element (WebElement): The element whose screenshot needs to be taken.
            path (str): path of file where to store the screenshot of image.
        """
        self.logger.info('\n')
        self.logger.info(f'Capturing screenshot of specific webelement.')
        element.screenshot(path)
        self.logger.info(f'Captured screenshot of specific webelement to {path}.\n')

    def scroll_into_view(self, value, by='xpath', timeout=10):
        """
        This scrolls to an element on the page. Can work with appium webviews.

        Args:
            value (str): The element search string.
            by (str): The method for applying the search string.
            timeout (int): The scroll duration.

        Returns:
            element (WebElement|None): The element in view.
        """
        self.logger.info('\n')
        self.logger.info(f'Scrolling to {value}.')
        if 'native' not in self.context.lower():
            element = self.find_element_explicitly(value, by, timeout=timeout)
            self.execute_script("arguments[0].scrollIntoView(true);", element)
            self.logger.info(f'Scrolled to {value}\n.')
            return element
        self.logger.info(f'Unable to js scroll due to the context to {self.context}.\n')

    def xpath_extraction(self, xpath):
        """"
        This will split the xpath into different attributes like class, name and value.

        Args:
            xpath: The element search string.
        """
        pieces = {}
        pieces['class'] = xpath.split('[')[0]
        attributes = re.findall(r'\[.*?\]', xpath)[0][1:-1]
        name, value = attributes.split('=')
        pieces['name'] = name
        pieces['new_name'] = re.sub(r'@', "", name)
        value = value[1:-1]
        pieces['value'] = value
        return pieces

    def path_conversion(self, value):
        """
        This will convert the Android element value into iOS & iOS to Android element value.

        Args:
            value: The element search string.
        """
        pieces = self.xpath_extraction(value)
        if self.platform_name in 'ios':
          mapping = {"text": "name", "content-desc": "name"}
          names = mapping[pieces['new_name']]
        else:
          # Conversion of iOS selectors to Android
          # mapping = {"name": ["text", "content-desc"]}
          names = [pieces['new_name']]

        at_value = pieces['value']
        if type(names) is not list:
            names = [names]
        if '//' in value:
             for n in names:
              return (f'//*[@{n}="{at_value}"]')
              break
        else:
            return (f'*[{n}="{at_value}"]')

    def special_cases(self, xpath):
        """
        This will convert the special cases in which Android element value(Only classname) into iOS & iOS(Only classname) to Android element value.

        Args:
            xpath: The element search string.
        """
        pieces = {}
        pieces['cla_name'] = xpath.split('[')[0]
        if self.platform_name in 'ios':
          mappings = {"//android.widget.EditText": "//XCUIElementTypeTextField", "//android.widget.Switch[1]": "//XCUIElementTypeButton", "//android.view.ViewGroup":'//XCUIElementTypeOther'}
          new_value = mappings[pieces['cla_name']]
        else:
          # Conversion of iOS selectors to Android
          # mappings = {"//XCUIElementTypeButton": "//android.widget.EditText", "//XCUIElementTypeTextField": "//android.widget.EditText"}
          new_value = pieces['cla_name']


        return new_value
