/*------------------------------------------------------------------------------
#
#	HelloWorld
#
#	Almost the simplest Magic Capª Package
#
#	General Magic Developer Technical Support
#	Copyright 1992-1997 General Magic, Inc.
#	All rights reserved.
#
------------------------------------------------------------------------------*/
 
/* Magic Cap System Software includes */
#include "Magic.h"
#include "Debug.h"

#include "HelloWorld.xh"
#include "HelloWorld.xph"

/*=================================================================================
						          Class Greeter
=================================================================================*/

#undef CURRENTCLASS
#define CURRENTCLASS Greeter

/* --------------------------------------------------------------------
	Here's the Draw() routine, which only needs to draw the content area, in 
	this case, it just fills a box.  This routine is called by the system when
	our object needs to be drawn.
*/

Method void
Greeter_Draw(Reference self)
{
	Box 		ourContentBox;
	ulong		color;

	/* Get an rgb color value from our viewable */
	color = PartColor(self, InheritedHighlighted(self) ? partAltContent : partContent);
	
	/* 	
		Now, get our contentBox and pass it and the color we want and the transfer
		mode to FillBox() .
	*/
	ContentBox(self, &ourContentBox);
	FillBox(CurrentCanvas(), CurrentClip(), &ourContentBox, color, pixelDither | pixelCopy);
}

#undef CURRENTCLASS
