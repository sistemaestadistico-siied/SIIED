// Inicializar Swiper
const swiper = new Swiper('.swiper-container', {
    // Configuración opcional
    loop: true,
    
    // Si queremos paginación
    pagination: {
        el: '.swiper-pagination',
        clickable: true,
    },
    
    // Botones de navegación
    navigation: {
        nextEl: '.swiper-button-next',
        prevEl: '.swiper-button-prev',
    },
    
    // Efecto de transición
    effect: 'slide',
    
    // Velocidad de transición
    speed: 600,
    
    // Autoplay
    autoplay: {
        delay: 5000,
        disableOnInteraction: false,
    },
});
