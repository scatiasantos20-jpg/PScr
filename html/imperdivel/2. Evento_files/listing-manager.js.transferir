jQuery(document).ready(function($) {
    'use strict';

    /**
     * Datepicker
     */
    $('.listing-manager-date-input').datepicker({
        dateFormat: 'yy-mm-dd'
    });

    $('.form-control.date').each(function() {
        $(this).datepicker({
            dateFormat: 'yy-mm-dd',
            numberOfMonths: 1,
            showButtonPanel: true
        });
    });

    /**
     * Chained
     */
    $('select.chained').each(function() {
        var id = $(this).attr('id');
        var to = $(this).data('chain-to');

        if (to) {
            to = $(this).closest('form').find('#' + to);
            $(this).closest('form').find('#' + id).chained(to);
        }
    });

    $('select.chained').each(function() {
        if ($(this).attr('disabled')) {
            $(this).closest('.form-group').hide().addClass('hidden');
        } else {
            $(this).closest('.form-group').show().removeClass('hidden');
        }

        $(this).on('change', function() {
            if ($(this).attr('disabled')) {
                $(this).closest('.form-group').hide().addClass('hidden');
            } else {
                $(this).closest('.form-group').show().removeClass('hidden');
            }
        });
    });

    /**
     * Autosubmit filter form
     */
    $('form.auto-submit-filter :input').on('change', function(e) {
        if (!$(this).closest('.map-wrapper').find('.map-container').hasClass('filter-live')) {
            $(this).closest('form').submit();
        }
    });

    /**
     * Typeahead
     */
    if ($.isFunction($.fn.typeahead)) {
        var typeahead_el = $('input[name=filter-keyword]');
        typeahead_el.typeahead({
            source: function (query, process) {
                return $.get(typeahead_el.data('ajax-action'), {
                    action: 'listing_manager_autocomplete',
                    query: query
                }, function (data) {
                    return process(data);
                });
            },
            select: function () {
              var val = this.$menu.find('.active').data('value');
              this.$element.data('active', val);
              if(this.autoSelect || val) {
                var newVal = this.updater(val);

                if (!newVal) {
                  newVal = "";
                }

                this.$element
                  .val(newVal.name)
                  .change();
                this.afterSelect(newVal);
              }

              window.location.href = newVal.link;
              return this.hide();
            },
            displayText: function(item) {
                return '<img src="' + item.image + '"><strong>' + item.name + '</strong>';
            },
            highlighter: function(item) {
                return unescape(item);
            },
            autoSelect: true
        });
    }

    /**
     * Favorite
     */
    $('.listing-manager-favorite-add').on('click', function(e) {
        e.preventDefault();
        var action = $(this).hasClass('marked') ? 'listing_manager_favorite_remove' : 'listing_manager_favorite_add';
        var toggler = $(this);

        $.ajax({
            url: toggler.data('ajax-url'),
            data: {
                'action': action,
                'id': toggler.data('listing-id')
            }
        }).done(function( data ) {
            if (data.success) {
                toggler.toggleClass('marked');
                var span = toggler.children('span');
                var toggleText = span.data('toggle');
                span.data('toggle', span.text());
                span.html(toggleText);
            } else {
                alert(data.message);
            }
        });
    });

    /**
     * Package switch
     */
    $('.listing-manager-submission-packages input[type=radio]').change(function() {
        $('.listing-manager-submission-packages input[type=radio]').removeAttr('checked');
        $(this).attr('checked', 'checked');
    });

   /**
    * Google Map Single
    */
    var mapObject = $('#map-object-single');

    if (mapObject.length) {
        var mapCenter = new google.maps.LatLng(mapObject.data('latitude'), mapObject.data('longitude'));
        var styles = mapObject.data('styles');
        var zoom = mapObject.data('zoom');
        var image = mapObject.data('image');

        var markers = [];
        var cluster = [{
            height: 36,
            width: 36
        }];
        var mapOptions = {
            center: mapCenter,
            styles: styles,
            zoom: zoom,
            scrollwheel: false,
            mapTypeControl: false,
            streetViewControl: false,
            zoomControl: false,
            mapTypeId: google.maps.MapTypeId.ROADMAP
        };

        var map = new google.maps.Map(document.getElementById('map-object-single'), mapOptions);
        var markerClusterer = new MarkerClusterer(map, markers, {styles: cluster});

        var marker = new RichMarker({
            flat: true,
            position: mapCenter,
            map: map,
            shadow: 0,
            content: '<div class="marker"><div class="marker-inner"><span class="marker-image" style="background-image: url(' + image + ')"></span></div></div>'
        });

        markers.push(marker);

    }

    /**
     * Claim button
     */
    var claim_btn_class = '.listing-manager-button-claim';
    $(document).on( 'click', claim_btn_class, function(e) {
        var action = 'listing_manager_ajax_can_claim';
        var success_url = $(this).attr('href');

        $.ajax({
            url: $(this).data('ajax-url'),
            data: {
                'action': action,
                'id': $(this).data('listing-id')
            }
        }).done(function( data ) {
            if (data.success) {
                window.location.href = success_url;
            } else {
                alert(data.message);
            }
        });

        e.preventDefault();
    });

    /**
     * Ratings
     */
    $('.listing-manager-rating').each(function() {
        var options = {
            theme: 'css-stars'
        };

        if ($(this).is('[readonly]')) {
            options.readonly = true;
        }

        $(this).barrating(options);
    });
});
