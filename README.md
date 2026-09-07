# YetAnotherAudioProject

Yet another nerd and personnal audio project to find the perfect sound with IEMs (In-Ear-Monitors, or fancy earphones), useful to nobody but me (_‘ω‘ _)!!  
See it as an expose or proof of concept.

In simple terms, hopefully, the goal of this project is to:

1.  Find what is the anatomically correct/best sound signature with IEMs (aka. frequency response) that should come to _my_ eardrums, and NOT the population average, using industry standard measurements.  
    This is not applicable with headphones as the pinna's transfer function is bypassed. Translation: the sound of the earphone has to preshot how the outer-ear (mine in this case) changes the sound, in order for the individual to have a good sound subjectively.  
    The whole point of this project is to estimate its contribution (usually from 3 kHz to 10 kHz..and above ?), so it can be simulated in the final frequency response.

2.  Find the IEM with **potentially** the closest sound to that ideal.

Technical explanation:  
Each IEM in the "neutral_fr" folder has been equalized so every frequency is the same volume in a sinesweep, except in the bass as its harder to tell.  
I made sure it follows more or less the preference bounds, so the tilt is coherent (-1dB/ocatve).

It has been done by ear and using 5128 data, so it can't come even close to what a measurement of the HRTF in the diffuse field of a lab can provide. But by averaging, my hope is to dilute HpTF effect (variation in frequency response not related to anatomy but the IEM load), as well as inaccuracies.

However, for that exact reason, a "one-fits-all" target does not exist, even at the individual scale: frequency response varies so much from individual to individual above 3k (so between 5128 measurements and on my head here) that the idea of single-line adherence becomes really irrelevant.
It is still insteresting to establish, as it
tells what sound signature on average my brain expects to hear.

Bass shelf level is arbitrary to match my current preference.

## Theory and Conjecture behind the project

I have been seeking for good sound quality in headphones and earphones for almost 10 years now. Over that time, I have noticed that answering "what is good sound?" is remarkably difficult. Not only is the hobby flooded with bias (eg. in reviews) and marketing BS, but nobody seems to truly agree.

Some will tell you it comes down to high detail retrieval, a wide soundstage, accurate timbre, and so on. While these terms are valid to describe a subjective experience, they cannot be measured objectively. Outfits like RTINGS or the MDAQS evaluation have tried to model these subjective criteria, such as scoring a headphone's soundstage, but these models are fundamentally based on their own conjecture (for instance, RTINGS assumes a direct causality between how open a headphone is/its low acoustic output impedance, and perceived soundstage width), and there is no consensus.

Others will claim it is about sticking closely to the Harman target. However, they forget that this target is the result of a *statistical* study: its lack of granularity completely masks the fine features a headphone response should have, especially in the treble. Furthermore, it was never designed as a strict benchmark, but as a general guideline. Harman claims that if a headphone closely matches the target, it has a significant probability of pleasing the majority, but it in no way guarantees optimal sound quality at the individual level (think of BMI: it works the same way). Finally, the measurement pinna used in the research literature was specifically modified for that study. The target makes no sense on a measurement rig that does not share that exact outer ear geometry, as the transfer function varies drastically depending on individual anatomy.

Here is the prevailing hypothesis shared by a significant part of the community, even though it has not yet been formally validated by scientific literature:

When listening to headphones, sound travels directly through the pinna and the ear canal straight to the eardrum. Subjectively, the sound does not originate from a specific external direction, meaning the tonal shift caused by the head-related transfer function (HRTF) remains constant even when turning your head.

Because of this, the **diffuse field** model becomes relevant. It represents a theoretical acoustic environment where sound remains identical regardless of the listener's orientation. We can therefore measure the subject's frequency response at the eardrum in a diffuse field: this is the DFHRTF (diffuse field head-related transfer function).

From there, you simply apply a downward tilt of roughly -1 dB per octave to obtain a subjectively pleasing balance. This concept comes from Harman's loudspeaker research, which showed that an ideal in-room response slopes down at about -1 dB/octave due to the acoustic properties of a standard, non-anechoic room. Ultimately, a headphone that reproduces this exact tilted frequency response would theoretically deliver an anatomically optimal sound.

In short, my goal with this project is to approximate this curve, then rank headphones and earphones based on how closely they adhere to this tilted DFHRTF.

Subjectively, EQing to smooth out all peaks and dips using a tone generator while broadly following this tilt yields an optimal musical timbre (what I have spent years searching for), lifting the veil of resonances and cancellations that previously colored the sound.

On the other hand, many audiophiles feel that this kind of tuning lacks of "technicalities", especially at lower listening levels due to the equal-loudness contours.

## Results

You can see the results here: https://iems.shewi.app/, or compile the project and run `web_ui.py`.