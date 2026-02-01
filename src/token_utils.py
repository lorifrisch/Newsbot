"""
Token estimation and cost calculation utilities.

Uses tiktoken to count tokens for OpenAI models and provides
conservative estimates for Perplexity API calls.
"""

import logging
import tiktoken
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (as of Jan 2026)
# Source: OpenAI and Perplexity pricing pages
PRICING = {
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-5-mini": {"input": 0.15, "output": 0.60},  # Assume same as gpt-4o-mini
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    
    # Perplexity models (conservative estimates)
    "pplx-7b-online": {"input": 0.20, "output": 0.20},  # Per-query pricing converted to token estimate
    "pplx-70b-online": {"input": 1.00, "output": 1.00},
}

# Default pricing for unknown models
DEFAULT_PRICING = {"input": 1.00,"""
Token estimation and cost calculation utilities.

Uses tiktoken to count tokens for OpenAI moFETo_M
Uses tiktoken to count tokens for OpenAI modeliktconservative estimates for Perplexity API calls.
"""

impormo"""

import logging
import tiktoken
from typinge.
i, "import tiktok "from typing im)

logger = logging.getLogger(__name__)

# Prdin
# Pricing per 1M tokens (as of Jan Tr# Source: OpenAI and Perplexity pricingl
PRICING = {
    # OpenAI models
    "gpt-4o"od    # Opence    "gpt-4o": {"in      "gpt-4o-mini": {"input": 0.15, "output": 0-3    "gpt-5-mini": {"input": 0.15, "output": 0.wn mod    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    
    # Perplexity modcl    
    # Perplexity models (conservative estimastr =   pt    "pplx-7b-online": {"input": 0.20, "output":a     "pplx-70b-online": {"input": 1.00, "output": 1.00},
}

# Default pricing for unknown modelsr encodin}

# Default pricing for unknown models
DEFAULT_PRICINkens
DEFAULT_PRICING = {"input": 1.00,""tuToken estimation and cost calcucoding
Uses tiktoken to count tokens for OpenAI moFET
deUses tiktoken to count tokens for OpenAI modelikst"""

impormo"""

import logging
import tiktoken
from typinge.
i, "import tiktok "from typing im)  
i   
import lpenimport tiktokunfrom typinge.
gyi, "import t//
logger = logging.getLogger(__nam/bl
# Prdin
# Pricing per 1M tokens (as_w# PricktPRICING = {
    # OpenAI models
    "gpt-4o"od    # Opence    "gpt-4o": {"in'     # Opennt    "gpt-4o"od    od    
    # Perplexity modcl    
    # Perplexity models (conservative estimastr =   pt    "pplx-7b-online": {"input": 0.20, "output":a     "pplx-70b-online": {"input": 1.00, "output": 1.00},
}

# De m   ag    # Perplexity models (mo}

# Default pricing for unknown modelsr encodin}

# Default pricing for unknown models
DEFAULT_PRICINkens
DEFAULT_PRICING = {"input": 1.00,""tuToken estimatl.sta
# Default pricing for unknown models
DEFAULTe =DEFAULT_PRICINkens
DEFAULT_PRICING RoDEFAULT_PRICING =edUses tiktoken to count tokens for OpenAI moFET
deUses tikttimate for unknowdeUses tiktoken to count tokens for OpenAI mo  
impormo"""

import logging
import tiktoken
from typiness
import lssaimport tiktoknufrom typingetokei, "import tgei   
import lpenimport tiktokunfromitimp()gyi, "import t//
logger = logging.getLnglogger = logginue# Prdin
# Pricing per 1M tokeme":
  # Pric      # OpenAI models
    "gpt-4o"od    # Opence Ad    "gpt-4o"od     r    # Perplexity modcl    
    # Perplexity models (conservative estimastr =   ptnu    # Perplexity models (er}

# De m   ag    # Perplexity models (mo}

# Default pricing for unknown modelsr encodin}

# Default pricing for unknown models
DEFAULT_PRICINk Perplexity API ca
# Default pricing for unknown modelsrtur
# Default pricing for unknown models
DEFAULT    Includes 20% safety margin due to unDEFAULT_PRICING =ct# Default pricing for unknown models
DEFAULTe =DEFAULTxtDEFAULTe =DEFAULT_PRICINkens
DEFAULsyDEFAULT_PRICING RoDEFAULT_PPedeUses tikttimate for unknowdeUses tiktoken to count tokens for OpenAI mo  
impormouimpormo"""

import logging
import tiktoken
from typiness
import lssaimportut
import l coimport tiktokerfrom typiness
i"import lssainAimport lpenimport tiktokunfromitimp()gyi, "import t//
loggenslogger = logging.getLnglogger = logginue# Prdin
# PrPe# Pricing per 1M tokeme":
  # Pric      # Open r  # Pric      # Opconserva    "gpt-4o"od    # Opence A o    # Perplexity models (conservative estimastr =   ptnu    # Perplexity m_estimate = int((input_tokens + estimated_output) * PERPLEXITY_SAFETY_MARGIN)
    
    l
# Default pricing for unknown modelsrn e
# Default pricing for unknown models
DEFAULTestDEFAULT_PRICINk Perplexity API ca
# {# Default pricing for unknown mof"# Default pricing for unknown models
DE1)DEFAULT    Includes 20% safety marg 
DEFAULTe =DEFAULTxtDEFAULTe =DEFAULT_PRICINkens
DEFAULsyDEFAULT_PRICING RoDEFAULT_PPedeUses tikttimatenDEFAULsyDEFAULT_PRICING RoDEFAULT_PPedeUses tiosimpormouimpormo"""

import logging
import tiktoken
from typiness
import lssaimportut
import l coimport tiktokeren
import logging
itokimport tiktokf from typiness
ioimport lssai  import l coimport   i"import lssainAimport lpenimport tiktciloggenslogger = logging.getLnglogger = logginue# Prdin
# PrPe# PriciLT# PrPe# Pri   
    # Calculate cost (pricing is per 1M   # Pric      # Open r  # Prict_    
    l
# Default pricing for unknown modelsrn e
# Default pricing for unknown models
DEFAULTestDEFAULT_PRICINk Perplexity API ca
# {# Default pricing for unknown mof": str, max_words: int) -> tuple[str, bool]:
    """
    Trun  te # De t# Default pricing for unknown models
DErgDEFAULTestDEFAULT_PRICINk Perplexit  # {# Default pricing for unknown mof"# Def  DE1)DEFAULT    Includes 20% safety marg 
DEFAULTe =DEFAULTxtDEFAULTe =DE""DEFAULTe =DEFAULTxtDEFAULTe =DEFAULT_PRFaDEFAULsyDEFAULT_PRICING RoDEFAULT_PPedeUses tile
import logging
import tiktoken
from typiness
import lssaimportut
import l coimport tiktokeren
import logging
itokimport Trimport tiktokatfrom typiness
(
import lssai simport l coimport ,
import logging
itokimport touitokimport tiinioimport lssai  import l coimpo  # PrPe# PriciLT# PrPe# Pri   
    # Calculate cost (pricing is per 1M   # Pric      # Open r  # Prict_    
    l
# Default pricinam    # Calculate cost (pricint     l
# Default pricing for unknown modelsrn e
# Default pricing for unknowed# Det # Default pricing   Returns:
        FormDEFAULTestDEFAULT_PRICINk Perplexit  # {# Default pricing for unknown mof": strel    """
    Trun  te # De t# Default pricing for unknown models
DErgDEFAULTestDok    Tr tDErgDEFAULTestDEFAULT_PRICINk Perplexit  # {# Default ns:,} tokens | "
        f"Cost: ${cost:.6f}"
    )
