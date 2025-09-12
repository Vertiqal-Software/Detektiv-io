import asyncio
import aiohttp
import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from app.models.intelligence import Company, WebsiteChange
from app.core.session import SessionLocal

logger = logging.getLogger(__name__)


class WebsiteMonitor:
    """
    Comprehensive website monitoring and change detection system.
    
    Monitors company websites for:
    - Content changes and updates
    - New blog posts and news
    - Technology stack changes
    - New certifications and partnerships
    - Product/service updates
    - Vendor mentions for competitive intelligence
    """
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.technology_patterns = self._load_technology_patterns()
        self.vendor_patterns = self._load_vendor_patterns()
        self.certification_patterns = self._load_certification_patterns()
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'Detecktiv.io Website Monitor/1.0 (+https://detecktiv.io/bot)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-GB,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def monitor_company_website(self, company_id: int) -> List[Dict]:
        """Monitor a company's website for changes and intelligence"""
        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company or not company.website:
                logger.warning(f"Company {company_id} has no website to monitor")
                return []
            
            website_url = self._normalize_url(company.website)
            logger.info(f"Monitoring website for {company.name}: {website_url}")
            
            # Discover and monitor key pages
            key_pages = await self._discover_key_pages(website_url)
            
            changes_detected = []
            for page_url in key_pages:
                try:
                    page_changes = await self._monitor_page(company, page_url, db)
                    if page_changes:
                        changes_detected.extend(page_changes)
                        
                    # Rate limiting between page requests
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error monitoring page {page_url}: {e}")
                    continue
            
            db.commit()
            
            if changes_detected:
                logger.info(f"Detected {len(changes_detected)} changes for {company.name}")
            
            return changes_detected
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error monitoring company {company_id}: {e}")
            return []
        finally:
            db.close()
    
    async def _discover_key_pages(self, base_url: str) -> List[str]:
        """Discover key pages to monitor on a website"""
        key_pages = [base_url]  # Always monitor homepage
        
        try:
            async with self.session.get(base_url) as response:
                if response.status != 200:
                    return key_pages
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for common important pages
                important_keywords = [
                    'about', 'news', 'blog', 'press', 'products', 'services',
                    'solutions', 'case-studies', 'customers', 'partners',
                    'certifications', 'awards', 'team', 'careers', 'contact'
                ]
                
                # Find navigation links
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if not href or href.startswith(('#', 'mailto:', 'tel:')):
                        continue
                    
                    absolute_url = urljoin(base_url, href)
                    
                    # Check if this is an internal link to an important page
                    if self._is_same_domain(base_url, absolute_url):
                        link_text = link.get_text().lower()
                        url_path = urlparse(absolute_url).path.lower()
                        
                        for keyword in important_keywords:
                            if keyword in link_text or keyword in url_path:
                                if absolute_url not in key_pages:
                                    key_pages.append(absolute_url)
                                break
                
                # Look for sitemap
                sitemap_urls = [
                    urljoin(base_url, '/sitemap.xml'),
                    urljoin(base_url, '/sitemap_index.xml')
                ]
                
                for sitemap_url in sitemap_urls:
                    try:
                        async with self.session.get(sitemap_url) as sitemap_response:
                            if sitemap_response.status == 200:
                                sitemap_content = await sitemap_response.text()
                                sitemap_pages = self._parse_sitemap(sitemap_content, base_url)
                                key_pages.extend(sitemap_pages[:10])  # Limit sitemap pages
                                break
                    except:
                        continue
                
        except Exception as e:
            logger.error(f"Error discovering pages for {base_url}: {e}")
        
        # Limit to reasonable number of pages to monitor
        return list(set(key_pages))[:15]
    
    async def _monitor_page(self, company: Company, page_url: str, db: Session) -> List[Dict]:
        """Monitor a specific page for changes"""
        try:
            async with self.session.get(page_url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {page_url}: {response.status}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                # Extract meaningful content
                content = soup.get_text()
                clean_content = self._clean_content(content)
                
                # Create content hash for change detection
                content_hash = hashlib.md5(clean_content.encode()).hexdigest()
                
                # Check if we've seen this page before
                last_change = db.query(WebsiteChange).filter(
                    WebsiteChange.company_id == company.id,
                    WebsiteChange.page_url == page_url
                ).order_by(WebsiteChange.detected_at.desc()).first()
                
                changes = []
                
                if last_change:
                    # Compare with previous version
                    if last_change.content_hash != content_hash:
                        change_details = self._analyze_content_changes(
                            last_change.content, clean_content
                        )
                        
                        if change_details['significant']:
                            # Detect intelligence indicators
                            intelligence = self._extract_intelligence(clean_content, page_url)
                            
                            change = WebsiteChange(
                                company_id=company.id,
                                page_url=page_url,
                                change_type=change_details['type'],
                                change_summary=change_details['summary'],
                                old_content=last_change.content[:5000],  # Limit stored content
                                new_content=clean_content[:5000],
                                content_hash=content_hash,
                                technologies_detected=intelligence.get('technologies', []),
                                vendors_mentioned=intelligence.get('vendors', []),
                                certifications_found=intelligence.get('certifications', []),
                                significance_score=self._calculate_significance_score(
                                    change_details, intelligence
                                )
                            )
                            
                            db.add(change)
                            changes.append(change)
                else:
                    # First time monitoring this page
                    intelligence = self._extract_intelligence(clean_content, page_url)
                    
                    change = WebsiteChange(
                        company_id=company.id,
                        page_url=page_url,
                        change_type='initial_scan',
                        change_summary=f'Initial scan of {urlparse(page_url).path}',
                        new_content=clean_content[:5000],
                        content_hash=content_hash,
                        technologies_detected=intelligence.get('technologies', []),
                        vendors_mentioned=intelligence.get('vendors', []),
                        certifications_found=intelligence.get('certifications', []),
                        significance_score=50.0  # Neutral score for initial scan
                    )
                    
                    db.add(change)
                    changes.append(change)
                
                return changes
                
        except Exception as e:
            logger.error(f"Error monitoring page {page_url}: {e}")
            return []
    
    def _analyze_content_changes(self, old_content: str, new_content: str) -> Dict:
        """Analyze changes between old and new content"""
        if not old_content:
            return {
                'significant': True,
                'type': 'content_added',
                'summary': 'New content detected'
            }
        
        # Simple change detection (in production, use more sophisticated diff)
        old_words = set(old_content.lower().split())
        new_words = set(new_content.lower().split())
        
        added_words = new_words - old_words
        removed_words = old_words - new_words
        
        # Calculate change percentage
        total_words = len(old_words.union(new_words))
        changed_words = len(added_words.union(removed_words))
        change_percentage = (changed_words / total_words * 100) if total_words > 0 else 0
        
        # Determine if change is significant
        significant = change_percentage > 5  # 5% change threshold
        
        # Analyze type of change
        if len(added_words) > len(removed_words):
            change_type = 'content_added'
            summary = f'New content added ({len(added_words)} new words)'
        elif len(removed_words) > len(added_words):
            change_type = 'content_removed'  
            summary = f'Content removed ({len(removed_words)} words removed)'
        else:
            change_type = 'content_modified'
            summary = f'Content modified ({change_percentage:.1f}% changed)'
        
        # Look for specific business-relevant changes
        business_keywords = [
            'contract', 'partnership', 'acquisition', 'merger', 'investment',
            'funding', 'award', 'certification', 'launch', 'product', 'service',
            'expansion', 'office', 'hire', 'appointment', 'customer', 'client'
        ]
        
        business_changes = []
        for word in added_words:
            if any(keyword in word.lower() for keyword in business_keywords):
                business_changes.append(word)
                significant = True
        
        if business_changes:
            summary += f' - Business keywords detected: {", ".join(business_changes[:5])}'
        
        return {
            'significant': significant,
            'type': change_type,
            'summary': summary,
            'change_percentage': change_percentage,
            'business_changes': business_changes
        }
    
    def _extract_intelligence(self, content: str, page_url: str) -> Dict:
        """Extract business intelligence from page content"""
        intelligence = {
            'technologies': [],
            'vendors': [],
            'certifications': []
        }
        
        content_lower = content.lower()
        
        # Detect technologies
        for tech_name, patterns in self.technology_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    intelligence['technologies'].append({
                        'name': tech_name,
                        'category': self._get_tech_category(tech_name),
                        'detected_via': 'content_analysis'
                    })
                    break
        
        # Detect vendor mentions
        for vendor_name, patterns in self.vendor_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    intelligence['vendors'].append({
                        'name': vendor_name,
                        'category': self._get_vendor_category(vendor_name),
                        'context': 'website_mention'
                    })
                    break
        
        # Detect certifications
        for cert_name, patterns in self.certification_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    intelligence['certifications'].append({
                        'name': cert_name,
                        'type': self._get_certification_type(cert_name),
                        'source_page': page_url
                    })
                    break
        
        return intelligence
    
    def _calculate_significance_score(self, change_details: Dict, intelligence: Dict) -> float:
        """Calculate significance score for a website change"""
        score = 50.0  # Base score
        
        # Change type scoring
        type_scores = {
            'content_added': 70,
            'content_modified': 60,
            'content_removed': 40,
            'initial_scan': 50
        }
        score = type_scores.get(change_details['type'], 50)
        
        # Business relevance boost
        if change_details.get('business_changes'):
            score += 20
        
        # Intelligence indicators boost
        if intelligence.get('technologies'):
            score += 10
        if intelligence.get('vendors'):
            score += 15  # Competitive intelligence is valuable
        if intelligence.get('certifications'):
            score += 15
        
        # Change magnitude
        change_pct = change_details.get('change_percentage', 0)
        if change_pct > 20:
            score += 15
        elif change_pct > 10:
            score += 10
        elif change_pct > 5:
            score += 5
        
        return min(100.0, max(0.0, score))
    
    def _clean_content(self, content: str) -> str:
        """Clean and normalize content for analysis"""
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Remove common noise words/phrases
        noise_patterns = [
            r'cookie policy',
            r'privacy policy', 
            r'terms and conditions',
            r'all rights reserved',
            r'copyright \d{4}',
            r'last updated',
            r'home\s+about\s+services\s+contact'  # Navigation menus
        ]
        
        for pattern in noise_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        return content.strip()
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL to standard format"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Remove trailing slash for consistency
        return url.rstrip('/')
    
    def _is_same_domain(self, base_url: str, check_url: str) -> bool:
        """Check if two URLs are from the same domain"""
        base_domain = urlparse(base_url).netloc.lower()
        check_domain = urlparse(check_url).netloc.lower()
        return base_domain == check_domain
    
    def _parse_sitemap(self, sitemap_content: str, base_url: str) -> List[str]:
        """Parse sitemap XML and extract relevant URLs"""
        urls = []
        try:
            soup = BeautifulSoup(sitemap_content, 'xml')
            
            # Handle both sitemap indexes and regular sitemaps
            for url_elem in soup.find_all(['url', 'sitemap']):
                loc_elem = url_elem.find('loc')
                if loc_elem:
                    url = loc_elem.text.strip()
                    if self._is_same_domain(base_url, url):
                        urls.append(url)
        except Exception as e:
            logger.error(f"Error parsing sitemap: {e}")
        
        return urls
    
    def _load_technology_patterns(self) -> Dict[str, List[str]]:
        """Load technology detection patterns"""
        return {
            'Microsoft Azure': [r'azure', r'microsoft cloud'],
            'AWS': [r'amazon web services', r'aws'],
            'Google Cloud': [r'google cloud', r'gcp'],
            'Office 365': [r'office 365', r'microsoft 365', r'o365', r'm365'],
            'Salesforce': [r'salesforce', r'sfdc'],
            'SAP': [r'\bsap\b', r'sap erp'],
            'Oracle': [r'oracle database', r'oracle cloud'],
            'VMware': [r'vmware', r'vsphere'],
            'Docker': [r'docker', r'container'],
            'Kubernetes': [r'kubernetes', r'k8s'],
            'SharePoint': [r'sharepoint'],
            'Teams': [r'microsoft teams', r'\bteams\b'],
            'Slack': [r'slack'],
            'Zoom': [r'zoom'],
            'Cisco': [r'cisco', r'webex'],
            'Dell': [r'dell emc', r'dell technologies'],
            'HPE': [r'hewlett packard enterprise', r'\bhpe\b'],
            'Lenovo': [r'lenovo', r'thinkpad', r'thinkcentre']
        }
    
    def _load_vendor_patterns(self) -> Dict[str, List[str]]:
        """Load vendor/competitor detection patterns"""
        return {
            'Microsoft': [r'microsoft', r'msft'],
            'Amazon': [r'amazon', r'aws'],
            'Google': [r'google', r'alphabet'],
            'IBM': [r'\bibm\b', r'international business machines'],
            'Accenture': [r'accenture'],
            'Deloitte': [r'deloitte'],
            'PwC': [r'pricewaterhousecoopers', r'\bpwc\b'],
            'KPMG': [r'kpmg'],
            'EY': [r'ernst & young', r'\bey\b'],
            'Capgemini': [r'capgemini'],
            'TCS': [r'tata consultancy', r'\btcs\b'],
            'Infosys': [r'infosys'],
            'Wipro': [r'wipro'],
            'Cognizant': [r'cognizant'],
            'HCL': [r'hcl technologies']
        }
    
    def _load_certification_patterns(self) -> Dict[str, List[str]]:
        """Load certification detection patterns"""
        return {
            'ISO 27001': [r'iso\s?27001', r'information security management'],
            'ISO 9001': [r'iso\s?9001', r'quality management'],
            'AWS Certified': [r'aws certified', r'amazon web services certified'],
            'Microsoft Certified': [r'microsoft certified', r'azure certified'],
            'Google Cloud Certified': [r'google cloud certified', r'gcp certified'],
            'ITIL': [r'itil', r'information technology infrastructure library'],
            'Prince2': [r'prince2', r'projects in controlled environments'],
            'PMP': [r'\bpmp\b', r'project management professional'],
            'Cyber Essentials': [r'cyber essentials'],
            'SOC 2': [r'soc 2', r'service organization control'],
            'GDPR Compliant': [r'gdpr compliant', r'general data protection regulation']
        }
    
    def _get_tech_category(self, tech_name: str) -> str:
        """Categorize detected technology"""
        categories = {
            'cloud': ['Microsoft Azure', 'AWS', 'Google Cloud'],
            'productivity': ['Office 365', 'Teams', 'Slack', 'Zoom'],
            'crm': ['Salesforce'],
            'erp': ['SAP', 'Oracle'],
            'infrastructure': ['VMware', 'Docker', 'Kubernetes'],
            'hardware': ['Dell', 'HPE', 'Lenovo', 'Cisco']
        }
        
        for category, technologies in categories.items():
            if tech_name in technologies:
                return category
        return 'other'
    
    def _get_vendor_category(self, vendor_name: str) -> str:
        """Categorize detected vendor"""
        categories = {
            'big_tech': ['Microsoft', 'Amazon', 'Google', 'IBM'],
            'consulting': ['Accenture', 'Deloitte', 'PwC', 'KPMG', 'EY', 'Capgemini'],
            'outsourcing': ['TCS', 'Infosys', 'Wipro', 'Cognizant', 'HCL']
        }
        
        for category, vendors in categories.items():
            if vendor_name in vendors:
                return category
        return 'other'
    
    def _get_certification_type(self, cert_name: str) -> str:
        """Categorize detected certification"""
        categories = {
            'security': ['ISO 27001', 'Cyber Essentials', 'SOC 2'],
            'quality': ['ISO 9001'],
            'cloud': ['AWS Certified', 'Microsoft Certified', 'Google Cloud Certified'],
            'process': ['ITIL', 'Prince2', 'PMP'],
            'compliance': ['GDPR Compliant']
        }
        
        for category, certs in categories.items():
            if cert_name in certs:
                return category
        return 'other'


async def monitor_companies_batch(company_ids: List[int]) -> Dict[int, List[Dict]]:
    """Monitor multiple companies' websites in batch"""
    results = {}
    
    async with WebsiteMonitor() as monitor:
        # Process companies with rate limiting
        semaphore = asyncio.Semaphore(5)  # Limit concurrent website requests
        
        async def monitor_with_semaphore(company_id: int):
            async with semaphore:
                try:
                    changes = await monitor.monitor_company_website(company_id)
                    results[company_id] = changes
                    # Rate limiting delay
                    await asyncio.sleep(2)  # 2 seconds between company requests
                except Exception as e:
                    logger.error(f"Error monitoring company {company_id}: {e}")
                    results[company_id] = []
        
        # Create tasks for all companies
        tasks = [monitor_with_semaphore(cid) for cid in company_ids]
        
        # Execute all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
    
    logger.info(f"Monitored {len(company_ids)} companies, found changes in {len([r for r in results.values() if r])} companies")
    return results